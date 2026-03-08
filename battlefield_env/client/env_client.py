"""
BattlefieldEnvClient — proper OpenEnv EnvClient subclass.

Uses the OpenEnv WebSocket protocol to communicate with BattlefieldEnvironment
via the HTTPEnvServer /ws endpoint.

Usage (synchronous context manager):
    with BattlefieldEnvClient("ws://localhost:8001") as client:
        result = client.reset(scenario_id="crossing_at_korzha")
        while not result.done:
            action = BattlefieldCombinedAction(
                attacker_action=BattlefieldAction(agent_role="attacker", actions=[...]),
                defender_action=BattlefieldAction(agent_role="defender", actions=[...]),
            )
            result = client.step(action)
        # result.observation, result.reward, result.done
        state = client.state()  # BattlefieldFullState (no fog)
"""
from __future__ import annotations

from typing import Any, Dict

from openenv.core import EnvClient
from openenv.core.env_client import StepResult

from battlefield.models import (
    BattlefieldCombinedAction,
    BattlefieldObservation,
    BattlefieldFullState,
)


class BattlefieldEnvClient(
    EnvClient[BattlefieldCombinedAction, BattlefieldObservation, BattlefieldFullState]
):
    """
    WebSocket client for BattlefieldEnvironment.

    Implements the three abstract methods required by openenv.core.EnvClient:
      _step_payload   — serialize BattlefieldCombinedAction → dict
      _parse_result   — deserialize server response → StepResult[BattlefieldObservation]
      _parse_state    — deserialize state response → BattlefieldFullState
    """

    def __init__(
        self,
        base_url: str = "ws://localhost:8001",
        connect_timeout_s: float = 10.0,
        message_timeout_s: float = 60.0,
    ) -> None:
        super().__init__(
            base_url=base_url,
            connect_timeout_s=connect_timeout_s,
            message_timeout_s=message_timeout_s,
        )

    # ── Abstract method implementations ──────────────────────────────────────

    def _step_payload(self, action: BattlefieldCombinedAction) -> Dict[str, Any]:
        """Serialize the combined action to the dict sent over the WebSocket."""
        return {"action": action.model_dump()}

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[BattlefieldObservation]:
        """Deserialize a step/reset response from the server."""
        obs_data = payload.get("observation", payload)
        obs = BattlefieldObservation(**obs_data)
        return StepResult(
            observation=obs,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> BattlefieldFullState:
        """Deserialize a state response from the server."""
        return BattlefieldFullState(**payload)
