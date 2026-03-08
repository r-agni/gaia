"""
GeoGuessLLMAgent -- think-then-act loop using HuggingFace Inference API.
"""
from __future__ import annotations

import asyncio
import os
from typing import List, Optional

from .hf_client import HFInferenceClient
from .output_parser import parse_llm_output
from .prompts import SYSTEM_PROMPT, observation_to_text
from geoguess.models import GeoGuessAction, GeoGuessObservation


class GeoGuessLLMAgent:
    """Single-agent LLM-powered GeoGuessr player."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        max_history: int = 4,
    ) -> None:
        self._model_id = model_id or os.environ.get(
            "HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct"
        )
        self._client = HFInferenceClient(
            api_key=os.environ.get("HF_API_KEY", ""),
            model_id=self._model_id,
        )
        self._history: List[dict] = []
        self._max_history = max_history

    def act(self, obs: GeoGuessObservation) -> GeoGuessAction:
        """Synchronous wrapper -- runs async call."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    fut = pool.submit(asyncio.run, self._async_act(obs))
                    return fut.result(timeout=30)
            return loop.run_until_complete(self._async_act(obs))
        except Exception:
            from .rule_agent import GeoGuessRuleAgent
            return GeoGuessRuleAgent().act(obs)

    async def _async_act(self, obs: GeoGuessObservation) -> GeoGuessAction:
        user_text = observation_to_text(obs)
        self._history.append({"role": "user", "content": user_text})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += self._history[-(self._max_history * 2):]

        response = await self._client.chat(
            messages=messages,
            max_new_tokens=512,
            temperature=0.7,
        )

        self._history.append({"role": "assistant", "content": response})
        return parse_llm_output(response)

    def reset(self) -> None:
        self._history = []
