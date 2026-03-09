"""
GeoGuessEnvironment — OpenEnv Environment subclass.

Wraps GeoGuessEngine with the openenv.core.Environment ABC interface so that
HTTPEnvServer can expose it via standard /reset, /step, /state, /schema,
/metadata, /health, and WS /ws routes.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from openenv.core import Environment
from openenv.core.env_server.types import EnvironmentMetadata
from openenv.core.client_types import StepResult

from .engine import GeoGuessEngine
from .models import (
    GeoGuessAction,
    GeoGuessFullState,
    GeoGuessObservation,
)


class GeoGuessEnvironment(
    Environment[GeoGuessAction, GeoGuessObservation, GeoGuessFullState]
):
    """
    OpenEnv-compatible GeoGuessr environment.

    Each instance holds one GeoGuessEngine (one episode).
    HTTPEnvServer creates a fresh instance per /reset call (stateless HTTP pattern).
    For the WebSocket training stream and /run_game, a shared engine is used
    (see server.py's _BroadcastingGeoGuessEnvironment).
    """

    def __init__(self) -> None:
        self._engine = GeoGuessEngine()

    @staticmethod
    def _run_coro_sync(coro):
        """
        Run async engine calls from sync OpenEnv handlers.
        HTTPEnvServer can execute handlers in worker threads with no event loop.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            tmp_loop = asyncio.new_event_loop()
            try:
                return tmp_loop.run_until_complete(coro)
            finally:
                tmp_loop.close()

        return loop.run_until_complete(coro)

    # ─── OpenEnv ABC ─────────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: int = 0,
        dataset_id: str = "world_cities_5k",
        total_rounds: int = 5,
        max_steps_per_round: int = 7,
        max_guesses_per_round: int = 2,
        location_id: Optional[str] = None,
        **kwargs,
    ) -> GeoGuessObservation:
        obs = self._run_coro_sync(
            self._engine.reset(
                dataset_id=dataset_id,
                total_rounds=total_rounds,
                max_steps_per_round=max_steps_per_round,
                max_guesses_per_round=max_guesses_per_round,
                seed=seed,
                location_id=location_id,
            )
        )
        obs.reward = None
        obs.done = False
        obs.metadata = {}
        return obs

    def step(self, action: GeoGuessAction, **kwargs) -> GeoGuessObservation:
        obs, reward, done = self._run_coro_sync(
            self._engine.step(action)
        )
        obs.reward = reward
        obs.done = done
        obs.metadata = {
            "episode_score": self._engine.state.episode_score if self._engine.state else 0.0,
            "current_round": self._engine.state.current_round if self._engine.state else 0,
        }
        return obs

    @property
    def state(self) -> GeoGuessFullState:
        d = self._engine.get_full_state_dict()
        return GeoGuessFullState(**d) if d else GeoGuessFullState()

    def get_metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            name="GeoGuessEnv",
            description=(
                "Single-agent GeoGuessr game. "
                "The agent identifies a secret real-world location by calling tools "
                "(street_view, terrain_analysis, weather, sun_angle, building_style, "
                "language_detection, globe_view) and submitting lat/lon guesses. "
                "Reward is Haversine distance score in [0, 1]."
            ),
            version="1.0.0",
        )
