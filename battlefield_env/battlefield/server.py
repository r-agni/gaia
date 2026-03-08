"""
OpenEnv-compatible FastAPI server for BattlefieldEnv.

Standard OpenEnv routes (registered by HTTPEnvServer):
  POST /reset        — init episode, returns BattlefieldObservation
  POST /step         — advance one tick, returns BattlefieldObservation
  GET  /state        — full (no fog) BattlefieldFullState for visualization
  GET  /schema       — JSON schema for action / observation types
  GET  /metadata     — environment name, description, version
  GET  /health       — health check
  WS   /ws           — WebSocket session (OpenEnv EnvClient protocol)

Custom routes (on top of OpenEnv):
  GET  /scenarios        — list available scenarios
  POST /run_episode      — run full episode with LLM agents, streams via WS
  WS   /ws/battlefield   — Cesium frontend real-time stream
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from openenv.core.env_server.http_server import HTTPEnvServer

from battlefield.engine import BattlefieldEngine
from battlefield.environment import BattlefieldEnvironment, _engine_state_to_pydantic
from battlefield.models import (
    BattlefieldCombinedAction,
    BattlefieldObservation,
)
from battlefield.scenarios import get_scenario, list_scenarios

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="BattlefieldEnv", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Register OpenEnv standard routes ────────────────────────────────────────

_openenv_server = HTTPEnvServer(
    env=BattlefieldEnvironment,
    action_cls=BattlefieldCombinedAction,
    observation_cls=BattlefieldObservation,
)
_openenv_server.register_routes(app)

# ─── Shared engine for custom routes ─────────────────────────────────────────
# The OpenEnv /reset and /step routes create a fresh BattlefieldEnvironment per
# request (stateless HTTP pattern).  For the Cesium WS stream and /run_episode
# we maintain a single shared engine.

_engine: Optional[BattlefieldEngine] = None
_ws_connections: set[WebSocket] = set()


def _serialize_full_state() -> dict:
    """Convert shared _engine state → JSON-serialisable dict for WS broadcast."""
    state = _engine_state_to_pydantic(_engine)
    return state.model_dump()


async def _broadcast(msg: dict) -> None:
    dead = set()
    for ws in _ws_connections:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    _ws_connections.difference_update(dead)


# ─── Custom REST endpoints ────────────────────────────────────────────────────


@app.get("/scenarios")
async def scenarios():
    return list_scenarios()


class RunEpisodeRequest(BaseModel):
    scenario_id: str = "crossing_at_korzha"
    max_ticks: Optional[int] = None
    tick_delay_ms: int = 500
    seed: int = 0


@app.post("/run_episode")
async def run_episode(req: RunEpisodeRequest):
    """
    Run a full episode with LLM agents (falls back to rule-based if HF_API_KEY not set).
    Streams state updates via WebSocket.  Returns episode summary when done.
    """
    global _engine
    from agents.rule_agent import RuleBasedAgent

    api_key = os.environ.get("HF_API_KEY", "")
    model_id = os.environ.get("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct")

    scenario = get_scenario(req.scenario_id)
    _engine = BattlefieldEngine(scenario, seed=req.seed)
    _engine.reset()

    if api_key:
        from agents.llm_agent import LLMAgent
        from agents.hf_client import HFInferenceClient
        hf = HFInferenceClient(model_id=model_id, api_key=api_key)
        attacker_agent = LLMAgent(role="attacker", hf_client=hf)
        defender_agent = LLMAgent(role="defender", hf_client=hf)
    else:
        attacker_agent = RuleBasedAgent(role="attacker")
        defender_agent = RuleBasedAgent(role="defender")

    max_ticks = req.max_ticks or scenario.max_ticks
    total_att_reward = 0.0
    total_def_reward = 0.0
    ticks_run = 0

    await _broadcast({"type": "episode_start", **_serialize_full_state()})

    for _ in range(max_ticks):
        att_obs = _engine.get_observation("attacker")
        def_obs = _engine.get_observation("defender")

        att_action, def_action = await asyncio.gather(
            attacker_agent.act(att_obs),
            defender_agent.act(def_obs),
        )

        _, att_r, def_r, done = _engine.step(att_action, def_action)
        total_att_reward += att_r
        total_def_reward += def_r
        ticks_run += 1

        await _broadcast({"type": "state_update", **_serialize_full_state()})

        if req.tick_delay_ms > 0:
            await asyncio.sleep(req.tick_delay_ms / 1000.0)

        if done:
            break

    await _broadcast({"type": "episode_end", "winner": _engine.state.winner, "ticks": ticks_run})

    return {
        "winner": _engine.state.winner,
        "ticks": ticks_run,
        "attacker_total_reward": round(total_att_reward, 3),
        "defender_total_reward": round(total_def_reward, 3),
    }


# ─── Auto-play (background continuous loop) ──────────────────────────────────

_auto_play_task: Optional[asyncio.Task] = None


class AutoPlayRequest(BaseModel):
    scenario_id: str = "crossing_at_korzha"
    tick_delay_ms: int = 800
    seed: int = 0
    use_llm: bool = False  # set True if HF_API_KEY is configured


@app.post("/auto_play/start")
async def auto_play_start(req: AutoPlayRequest):
    """Start a continuous background episode loop (rule-based or LLM agents)."""
    global _auto_play_task
    if _auto_play_task and not _auto_play_task.done():
        return {"status": "already_running"}

    async def _loop():
        global _engine
        from agents.rule_agent import RuleBasedAgent
        api_key = os.environ.get("HF_API_KEY", "")

        episode = 0
        while True:
            episode += 1
            scenario = get_scenario(req.scenario_id)
            _engine = BattlefieldEngine(scenario, seed=req.seed + episode)
            _engine.reset()

            if req.use_llm and api_key:
                from agents.llm_agent import LLMAgent
                from agents.hf_client import HFInferenceClient
                hf = HFInferenceClient(
                    model_id=os.environ.get("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct"),
                    api_key=api_key,
                )
                att = LLMAgent(role="attacker", hf_client=hf)
                dfn = LLMAgent(role="defender", hf_client=hf)
            else:
                att = RuleBasedAgent(role="attacker")
                dfn = RuleBasedAgent(role="defender")

            await _broadcast({"type": "episode_start", "episode": episode, **_serialize_full_state()})

            for _ in range(scenario.max_ticks):
                att_obs = _engine.get_observation("attacker")
                def_obs = _engine.get_observation("defender")
                att_action, def_action = await asyncio.gather(att.act(att_obs), dfn.act(def_obs))
                _, _, _, done = _engine.step(att_action, def_action)
                await _broadcast({"type": "state_update", **_serialize_full_state()})
                if req.tick_delay_ms > 0:
                    await asyncio.sleep(req.tick_delay_ms / 1000.0)
                if done:
                    break

            await _broadcast({"type": "episode_end", "episode": episode, "winner": _engine.state.winner})
            # Brief pause between episodes
            await asyncio.sleep(2.0)

    _auto_play_task = asyncio.create_task(_loop())
    return {"status": "started"}


@app.post("/auto_play/stop")
async def auto_play_stop():
    """Stop the continuous background episode loop."""
    global _auto_play_task
    if _auto_play_task and not _auto_play_task.done():
        _auto_play_task.cancel()
        _auto_play_task = None
        return {"status": "stopped"}
    return {"status": "not_running"}


@app.get("/auto_play/status")
async def auto_play_status():
    running = _auto_play_task is not None and not _auto_play_task.done()
    tick = _engine.state.tick if (_engine and _engine.state) else -1
    return {"running": running, "tick": tick}


# ─── Cesium WebSocket stream ──────────────────────────────────────────────────

@app.websocket("/ws/battlefield")
async def battlefield_ws(websocket: WebSocket):
    """
    Real-time state stream for Cesium frontend.
    Separate from the OpenEnv /ws endpoint (which is for EnvClient training).
    """
    await websocket.accept()
    _ws_connections.add(websocket)
    if _engine and _engine.state:
        await websocket.send_json({"type": "state_update", **_serialize_full_state()})
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        _ws_connections.discard(websocket)
