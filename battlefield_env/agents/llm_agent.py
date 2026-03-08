"""
LLMAgent — think-then-act loop using HuggingFace Inference API.
Same model is used for both roles; role is differentiated via system prompt.
"""
from __future__ import annotations

import logging
from typing import Literal

from agents.hf_client import HFInferenceClient
from agents.output_parser import parse_llm_output
from agents.prompts import (
    ATTACKER_SYSTEM_PROMPT,
    DEFENDER_SYSTEM_PROMPT,
    observation_to_text,
)
from battlefield.models import (
    _BattlefieldActionInternal as BattlefieldAction,
    _BattlefieldObsInternal as BattlefieldObservation,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS = {
    "attacker": ATTACKER_SYSTEM_PROMPT,
    "defender": DEFENDER_SYSTEM_PROMPT,
}

# Rolling conversation window (number of prior turns to keep)
MAX_HISTORY_TURNS = 3


class LLMAgent:
    def __init__(
        self,
        role: Literal["attacker", "defender"],
        hf_client: HFInferenceClient,
        temperature: float = 0.7,
        max_new_tokens: int = 600,
    ):
        self.role = role
        self._client = hf_client
        self._temperature = temperature
        self._max_new_tokens = max_new_tokens
        self._system_prompt = SYSTEM_PROMPTS[role]
        self._history: list[dict] = []   # alternating user/assistant turns

    async def act(self, obs: BattlefieldObservation) -> BattlefieldAction:
        """
        1. Convert observation to natural language briefing.
        2. Build message list: [system, ...last N turns, new user turn].
        3. Call HF Inference API.
        4. Append to history.
        5. Parse response → BattlefieldAction.
        """
        briefing = observation_to_text(obs)

        # Keep last MAX_HISTORY_TURNS pairs (user+assistant = 2 messages per turn)
        trimmed_history = self._history[-(MAX_HISTORY_TURNS * 2):]

        messages = [
            {"role": "system", "content": self._system_prompt},
            *trimmed_history,
            {"role": "user", "content": briefing},
        ]

        try:
            raw = await self._client.chat(
                messages,
                max_new_tokens=self._max_new_tokens,
                temperature=self._temperature,
            )
        except Exception as e:
            logger.error("HF API error for %s agent: %s", self.role, e)
            raw = "REASONING: API error, holding position.\nACTIONS: []"

        # Append to rolling history
        self._history.append({"role": "user", "content": briefing})
        self._history.append({"role": "assistant", "content": raw})

        known_ids = [u.unit_id for u in obs.own_units]
        action = parse_llm_output(raw, self.role, obs.tick, known_ids)

        logger.info(
            "[tick %d] %s REASONING: %s",
            obs.tick, self.role.upper(), action.reasoning[:120],
        )
        logger.debug("[tick %d] %s ACTIONS: %s", obs.tick, self.role.upper(), action.actions)

        return action

    def reset(self) -> None:
        """Clear conversation history (call between episodes)."""
        self._history = []
