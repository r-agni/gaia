"""
Robust extraction of GeoGuessAction from LLM text output.
Handles markdown fences, trailing commas, single quotes, etc.
"""
from __future__ import annotations

import json
import re

from geoguess.models import AVAILABLE_TOOLS, GeoGuessAction


def parse_llm_output(text: str) -> GeoGuessAction:
    """
    Extract a GeoGuessAction from raw LLM output text.
    Falls back to a centroid guess on parse failure.
    """
    for match in re.finditer(r'\{[^{}]+\}', text, re.DOTALL):
        raw = match.group()
        try:
            obj = _safe_json(raw)
            if obj.get("action_type") == "tool_call":
                tool_name = obj.get("tool_name", "")
                if tool_name not in AVAILABLE_TOOLS:
                    continue
                return GeoGuessAction(
                    action_type="tool_call",
                    tool_name=tool_name,
                    tool_params=obj.get("tool_params", {}),
                    reasoning=obj.get("reasoning", ""),
                )
            elif obj.get("action_type") == "guess":
                return GeoGuessAction(
                    action_type="guess",
                    guess_lat=float(obj.get("guess_lat", 0)),
                    guess_lon=float(obj.get("guess_lon", 0)),
                    reasoning=obj.get("reasoning", ""),
                )
        except Exception:
            continue

    # Fallback centroid guess
    return GeoGuessAction(
        action_type="guess",
        guess_lat=20.0,
        guess_lon=15.0,
        reasoning="[parse failure fallback]",
    )


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    repaired = text.replace("'", '"')
    repaired = re.sub(r',\s*([\]}])', r'\1', repaired)
    return json.loads(repaired)
