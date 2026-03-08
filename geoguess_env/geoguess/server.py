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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
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


def _serialize_full_state() -> dict:
    if _engine is None:
        return {}
    return _engine.get_full_state_dict()


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
