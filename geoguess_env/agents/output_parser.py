"""
Robust extraction of GeoGuessAction from LLM text output.
Handles markdown fences, trailing commas, single quotes, etc.
"""
from __future__ import annotations

import ast
import json
import math
import re

from geoguess.models import AVAILABLE_TOOLS, GeoGuessAction


def parse_llm_output(text: str) -> GeoGuessAction:
    """
    Extract a GeoGuessAction from raw LLM output text.
    Falls back to a centroid guess on parse failure.
    """
    actions = parse_llm_actions(text)
    if actions:
        return actions[0]

    # Fallback centroid guess
    return GeoGuessAction(
        action_type="guess",
        guess_lat=20.0,
        guess_lon=15.0,
        reasoning="[parse failure fallback]",
    )


def parse_llm_actions(text: str) -> list[GeoGuessAction]:
    """
    Extract all valid GeoGuessAction objects from raw LLM output text.
    Invalid or incomplete action payloads are skipped.
    """
    actions: list[GeoGuessAction] = []
    for raw in _extract_balanced_json_objects(text):
        try:
            obj = _safe_json(raw)
        except Exception:
            continue

        action = _action_from_obj(obj)
        if action is not None:
            actions.append(action)
    return actions


def _action_from_obj(obj: dict) -> GeoGuessAction | None:
    action_type = str(obj.get("action_type", "")).strip().lower()
    if action_type == "tool_call":
        tool_name = str(obj.get("tool_name", "")).strip()
        if tool_name not in AVAILABLE_TOOLS:
            return None
        tool_params = obj.get("tool_params", {})
        if not isinstance(tool_params, dict):
            tool_params = {}
        return GeoGuessAction(
            action_type="tool_call",
            tool_name=tool_name,
            tool_params=tool_params,
            reasoning=str(obj.get("reasoning", "")),
        )

    if action_type == "guess":
        coords = _coerce_guess_coords(obj)
        if coords is None:
            return None
        guess_lat, guess_lon = coords
        return GeoGuessAction(
            action_type="guess",
            guess_lat=guess_lat,
            guess_lon=guess_lon,
            reasoning=str(obj.get("reasoning", "")),
        )

    return None


def _coerce_guess_coords(obj: dict) -> tuple[float, float] | None:
    lat = _first_float(obj, ("guess_lat", "lat", "latitude"))
    lon = _first_float(obj, ("guess_lon", "lon", "longitude", "lng"))
    if lat is None or lon is None:
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    lat = max(-90.0, min(90.0, lat))
    lon = max(-180.0, min(180.0, lon))
    return lat, lon


def _first_float(obj: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in obj:
            continue
        try:
            return float(obj[key])
        except (TypeError, ValueError):
            continue
    return None


def _extract_balanced_json_objects(text: str) -> list[str]:
    """
    Return balanced {...} spans from free-form text, ignoring braces inside strings.
    """
    spans: list[str] = []
    start_idx: int | None = None
    depth = 0
    in_string = False
    quote_char = '"'
    escaped = False

    for idx, ch in enumerate(text):
        if depth == 0:
            if ch == "{":
                start_idx = idx
                depth = 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote_char:
                in_string = False
            continue

        if ch in ('"', "'"):
            in_string = True
            quote_char = ch
            continue

        if ch == "{":
            depth += 1
            continue

        if ch == "}":
            depth -= 1
            if depth == 0 and start_idx is not None:
                spans.append(text[start_idx:idx + 1])
                start_idx = None

    return spans


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    repaired = _repair_json(text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Python literal fallback helps with single-quoted dicts from chat models.
    obj = ast.literal_eval(text)
    if isinstance(obj, dict):
        return obj

    raise ValueError("Parsed object is not a dict")


def _repair_json(text: str) -> str:
    repaired = text.replace("'", '"')
    repaired = re.sub(r",\s*([\]}])", r"\1", repaired)
    return repaired
