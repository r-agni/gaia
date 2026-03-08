"""
OpenEnv-compatible FastAPI server for GeoGuessEnv.

Standard OpenEnv routes (registered by HTTPEnvServer):
  POST /reset        -- init episode, returns GeoGuessObservation
  POST /step         -- advance one step, returns GeoGuessObservation
  GET  /state        -- full GeoGuessFullState for visualization
  GET  /schema       -- JSON schema for action / observation types
  GET  /metadata     -- environment name, description, version
  GET  /health       -- health check
  WS   /ws           -- WebSocket session (OpenEnv EnvClient / training protocol)

Custom routes:
  GET  /datasets          -- list available location datasets
  POST /run_game          -- run full game with LLM/rule agents, streams via WS
  POST /auto_play/start   -- start continuous loop of games
  POST /auto_play/stop    -- stop background loop
  GET  /auto_play/status  -- {running, round, episode}
  GET  /training/status   -- {episode, round, training_mode}
  GET  /training/history  -- accumulated episode history for results view
  WS   /ws/geoguess       -- Cesium frontend real-time stream
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from openenv.core.env_server.http_server import HTTPEnvServer

from .engine import GeoGuessEngine
from .environment import GeoGuessEnvironment
from .locations import list_datasets
from .models import GeoGuessAction, GeoGuessObservation

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="GeoGuessEnv", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Shared engine for custom routes ─────────────────────────────────────────

_engine: Optional[GeoGuessEngine] = None
_ws_connections: set[WebSocket] = set()
_training_episode: int = 0
_auto_play_task: Optional[asyncio.Task] = None
_episode_history: list[dict] = []
_MAX_HISTORY = 500
_hf_space_webhook_url = os.environ.get("HF_SPACE_WEBHOOK_URL", "").strip()
_training_status_file = os.environ.get("TRAINING_STATUS_FILE", "/tmp/gaia_training_status.json")
_hf_sync_status: dict = {
    "enabled": bool(_hf_space_webhook_url),
    "webhook_url_set": bool(_hf_space_webhook_url),
    "last_attempt_ts": None,
    "last_ok": None,
    "last_status_code": None,
    "last_error": None,
}


def _serialize_full_state() -> dict:
    if _engine is None:
        return {}
    return _engine.get_full_state_dict()


def _read_training_runtime_status() -> dict:
    status = {
        "status_file": _training_status_file,
        "present": False,
        "state": "unknown",
        "message": "No runtime status file found.",
        "timestamp": None,
    }
    try:
        if os.path.exists(_training_status_file):
            with open(_training_status_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                status.update(data)
                status["present"] = True
    except Exception as e:
        status["state"] = "error"
        status["message"] = f"Failed to parse runtime status file: {e}"
    return status


async def _forward_episode_to_hf_space(episode_payload: dict) -> None:
    """Best-effort webhook POST for external mirrors (e.g., HF Space backend)."""
    global _hf_sync_status
    if not _hf_space_webhook_url:
        return
    body = {
        "source": "gaia",
        "event_type": "episode_end",
        "event_ts": time.time(),
        "episode": episode_payload,
    }
    _hf_sync_status["last_attempt_ts"] = time.time()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.post(_hf_space_webhook_url, json=body)
        _hf_sync_status["last_status_code"] = r.status_code
        _hf_sync_status["last_ok"] = 200 <= r.status_code < 300
        _hf_sync_status["last_error"] = None if _hf_sync_status["last_ok"] else f"HTTP {r.status_code}"
    except Exception as e:
        _hf_sync_status["last_status_code"] = None
        _hf_sync_status["last_ok"] = False
        _hf_sync_status["last_error"] = str(e)


async def _broadcast(msg: dict) -> None:
    dead: set[WebSocket] = set()
    data = json.dumps(msg)
    for ws in list(_ws_connections):
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _ws_connections.difference_update(dead)


def _schedule_broadcast(msg: dict) -> None:
    """Fire-and-forget broadcast safe to call from synchronous contexts."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_broadcast(msg))
        else:
            loop.run_until_complete(_broadcast(msg))
    except Exception:
        pass


# ─── Broadcasting environment (training integration) ────────────────────────


class _BroadcastingGeoGuessEnvironment(GeoGuessEnvironment):
    """
    Wraps GeoGuessEnvironment so that training steps (via OpenEnv /ws)
    are broadcast to the Cesium frontend WebSocket in real time.
    """

    def reset(self, **kwargs):
        global _engine, _training_episode
        _training_episode += 1
        obs = super().reset(**kwargs)
        _engine = self._engine
        _schedule_broadcast({
            "type": "episode_start",
            "episode": _training_episode,
            "training_mode": True,
            **_serialize_full_state(),
        })
        return obs

    def step(self, action, **kwargs):
        global _engine
        result = super().step(action, **kwargs)
        _engine = self._engine
        state_dict = _serialize_full_state()

        # Emit a dedicated oversight_flag event when new flags are raised
        msg_type = "state_update"
        if state_dict.get("oversight_flags"):
            msg_type = "oversight_flag"

        _schedule_broadcast({
            "type": msg_type,
            "episode": _training_episode,
            "training_mode": True,
            **state_dict,
        })
        return result


# ─── Register OpenEnv standard routes ────────────────────────────────────────

_openenv_server = HTTPEnvServer(
    env=_BroadcastingGeoGuessEnvironment,
    action_cls=GeoGuessAction,
    observation_cls=GeoGuessObservation,
)
_openenv_server.register_routes(app)


# ─── Custom REST endpoints ────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Simple health check for start.sh and load balancers."""
    return {"status": "ok"}


@app.get("/game/state")
async def game_state():
    """Full game state for frontend polling."""
    return _serialize_full_state()


@app.get("/game/scene_image")
async def game_scene_image():
    """Street View image for the current round's secret location. Returns 404 if no engine, no round, or no API key."""
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not google_key or _engine is None or _engine.state is None:
        return Response(status_code=404)
    s = _engine.state
    if s.current_round >= len(s.rounds):
        return Response(status_code=404)
    round_state = s.rounds[s.current_round]
    loc = round_state.location
    sv_url = (
        f"https://maps.googleapis.com/maps/api/streetview"
        f"?size=400x400&location={loc.lat},{loc.lon}"
        f"&fov=90&heading=0&pitch=0&key={google_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            img_r = await client.get(sv_url)
            if img_r.status_code != 200 or len(img_r.content) < 5000:
                return Response(status_code=404)
            return Response(
                content=img_r.content,
                media_type=img_r.headers.get("content-type", "image/jpeg"),
            )
    except Exception:
        return Response(status_code=404)


@app.get("/datasets")
async def datasets():
    return list_datasets()


@app.get("/training/status")
async def training_status():
    state = _engine.state if _engine else None
    return {
        "episode": _training_episode,
        "round": state.current_round if state else -1,
        "training_mode": _training_episode > 0,
    }


@app.get("/training/history")
async def training_history():
    """Return accumulated episode history for the training results view."""
    return {
        "episodes": _episode_history,
        "total_episodes": len(_episode_history),
    }


@app.get("/training/runtime_status")
async def training_runtime_status():
    """Return launcher/runtime status for GRPO + optional HF webhook forwarding."""
    return {
        "run_grpo_training_env": os.environ.get("RUN_GRPO_TRAINING", "").lower() == "true",
        "runtime_status": _read_training_runtime_status(),
        "hf_space_sync": _hf_sync_status,
    }


@app.get("/oversight/summary")
async def oversight_summary():
    """Return the oversight agent's current episode summary."""
    state_dict = _serialize_full_state()
    return {
        "episode": _training_episode,
        "oversight_summary": state_dict.get("oversight_summary", {}),
        "current_round_flags": state_dict.get("oversight_flags", []),
    }


class RunGameRequest(BaseModel):
    dataset_id: str = "world_cities_5k"
    total_rounds: int = 5
    max_steps_per_round: int = 7
    max_guesses_per_round: int = 2
    step_delay_ms: int = 500
    seed: int = 0
    use_llm: bool = False


async def _run_game_impl(req: RunGameRequest):
    """Run one game to completion; broadcasts state via WebSocket. Used by POST /run_game and auto_play."""
    global _engine
    from agents.rule_agent import GeoGuessRuleAgent
    agent: GeoGuessRuleAgent

    if req.use_llm:
        try:
            from agents.llm_agent import GeoGuessLLMAgent
            agent = GeoGuessLLMAgent()
        except Exception:
            from agents.rule_agent import GeoGuessRuleAgent
            agent = GeoGuessRuleAgent()
    else:
        from agents.rule_agent import GeoGuessRuleAgent
        agent = GeoGuessRuleAgent()

    engine = GeoGuessEngine()
    _engine = engine

    obs = await engine.reset(
        dataset_id=req.dataset_id,
        total_rounds=req.total_rounds,
        max_steps_per_round=req.max_steps_per_round,
        max_guesses_per_round=req.max_guesses_per_round,
        seed=req.seed,
    )

    await _broadcast({"type": "episode_start", **engine.get_full_state_dict()})

    done = False
    round_scores = []
    while not done:
        action = agent.act(obs)
        obs, reward, done = await engine.step(action)
        state_dict = engine.get_full_state_dict()

        if obs.done or reward > 0:
            await _broadcast({"type": "round_end", "reward": reward, **state_dict})
        elif state_dict.get("oversight_flags"):
            await _broadcast({"type": "oversight_flag", **state_dict})
        else:
            await _broadcast({"type": "state_update", **state_dict})

        if reward > 0:
            round_scores.append(reward)

        if req.step_delay_ms > 0:
            await asyncio.sleep(req.step_delay_ms / 1000)

    await _broadcast({"type": "episode_end", **engine.get_full_state_dict()})

    # Record episode in history
    final = engine.get_full_state_dict()
    distances = []
    for rh in final.get("round_history", []):
        d = rh.get("distance_km")
        if d is not None:
            distances.append(d)
    _episode_history.append({
        "episode_id": final.get("episode_id", ""),
        "episode_number": len(_episode_history) + 1,
        "episode_score": final.get("episode_score", 0),
        "total_rounds": final.get("total_rounds", 0),
        "avg_distance_km": round(sum(distances) / len(distances), 1) if distances else None,
        "min_distance_km": round(min(distances), 1) if distances else None,
        "rounds": final.get("round_history", []),
        "oversight_summary": final.get("oversight_summary", {}),
        "timestamp": time.time(),
    })
    if len(_episode_history) > _MAX_HISTORY:
        _episode_history[:] = _episode_history[-_MAX_HISTORY:]
    await _forward_episode_to_hf_space(_episode_history[-1])


@app.post("/run_game")
async def run_game(req: RunGameRequest):
    """Start a game in the background; returns immediately. State streams via WebSocket."""
    asyncio.create_task(_run_game_impl(req))
    return {"status": "started"}


@app.post("/auto_play/start")
async def auto_play_start(req: RunGameRequest):
    global _auto_play_task, _training_episode

    async def _loop():
        global _training_episode
        seed = req.seed
        while True:
            _training_episode += 1
            await _run_game_impl(RunGameRequest(
                dataset_id=req.dataset_id,
                total_rounds=req.total_rounds,
                max_steps_per_round=req.max_steps_per_round,
                max_guesses_per_round=req.max_guesses_per_round,
                step_delay_ms=req.step_delay_ms,
                seed=seed,
                use_llm=req.use_llm,
            ))
            seed += 1
            await asyncio.sleep(0.5)

    if _auto_play_task and not _auto_play_task.done():
        _auto_play_task.cancel()
    _auto_play_task = asyncio.create_task(_loop())
    return {"status": "started"}


@app.post("/auto_play/stop")
async def auto_play_stop():
    global _auto_play_task
    if _auto_play_task and not _auto_play_task.done():
        _auto_play_task.cancel()
        _auto_play_task = None
    return {"status": "stopped"}


@app.get("/auto_play/status")
async def auto_play_status():
    running = bool(_auto_play_task and not _auto_play_task.done())
    state = _engine.state if _engine else None
    return {
        "running": running,
        "round": state.current_round if state else -1,
        "episode": _training_episode,
    }


# ─── Cesium frontend WebSocket ────────────────────────────────────────────────


@app.websocket("/ws/geoguess")
async def ws_geoguess(websocket: WebSocket):
    await websocket.accept()
    _ws_connections.add(websocket)
    try:
        if _engine is not None:
            try:
                await websocket.send_text(
                    json.dumps({"type": "state_update", **_serialize_full_state()})
                )
            except Exception:
                pass
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except Exception:
                pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _ws_connections.discard(websocket)
