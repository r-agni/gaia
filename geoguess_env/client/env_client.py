"""
GeoGuessEnvClient -- OpenEnv EnvClient subclass.

Connects to the GeoGuessEnv server via the OpenEnv WebSocket protocol (/ws).
Used by training scripts and external agents.
"""
from __future__ import annotations

from typing import Optional

from openenv.core.env_client import EnvClient
from openenv.core.client_types import StepResult

from geoguess.models import GeoGuessAction, GeoGuessFullState, GeoGuessObservation


class GeoGuessEnvClient(
    EnvClient[GeoGuessAction, GeoGuessObservation, GeoGuessFullState]
):
    """
    WebSocket client for GeoGuessEnv.

    Usage:
        client = GeoGuessEnvClient(base_url="ws://localhost:8001")
        obs = client.reset(dataset_id="world_cities_5k", total_rounds=5)
        result = client.step(GeoGuessAction(action_type="tool_call", tool_name="weather"))
    """

    def __init__(
        self,
        base_url: str = "ws://localhost:8001",
        connect_timeout_s: float = 30.0,
        message_timeout_s: float = 60.0,
    ) -> None:
        super().__init__(
            base_url=base_url,
            connect_timeout_s=connect_timeout_s,
            message_timeout_s=message_timeout_s,
        )

    # ─── OpenEnv EnvClient abstract methods ──────────────────────────────────

    def _step_payload(self, action: GeoGuessAction) -> dict:
        return action.model_dump()

    def _parse_result(self, payload: dict) -> StepResult[GeoGuessObservation]:
        obs_data = payload.get("observation", payload)
        obs = GeoGuessObservation(**{
            k: v for k, v in obs_data.items()
            if k in GeoGuessObservation.model_fields
        })
        obs.reward = payload.get("reward", 0.0)
        obs.done = payload.get("done", False)
        obs.metadata = payload.get("metadata", {})
        return StepResult(observation=obs, reward=obs.reward, done=obs.done)

    def _parse_state(self, payload: dict) -> GeoGuessFullState:
        return GeoGuessFullState(**{
            k: v for k, v in payload.items()
            if k in GeoGuessFullState.model_fields
        })
