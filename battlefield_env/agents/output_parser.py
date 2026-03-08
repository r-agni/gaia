"""
Robust extraction of REASONING and ACTIONS from LLM text output.
Handles markdown code fences, trailing commas, single quotes, etc.
Falls back to WaitAction list if nothing valid can be parsed.
"""
from __future__ import annotations

import json
import logging
import re
from typing import List, Tuple

from battlefield.models import (
    ACTION_CLASSES,
    AttackAction,
    _BattlefieldActionInternal as BattlefieldAction,
    CallSupportAction,
    DeployAction,
    DigInAction,
    GridPos,
    MoveAction,
    RetreatAction,
    ScoutAction,
    WaitAction,
)

logger = logging.getLogger(__name__)


def _clean_json(text: str) -> str:
    """Pre-process common LLM JSON formatting issues."""
    # Remove markdown code fences
    text = re.sub(r"```(?:json)?", "", text)
    text = text.replace("```", "")
    # Replace single quotes around keys/values (careful not to break apostrophes)
    text = re.sub(r"'([^']+)':", r'"\1":', text)
    text = re.sub(r": '([^']*)'", r': "\1"', text)
    # Remove trailing commas before ] or }
    text = re.sub(r",\s*([\]}])", r"\1", text)
    return text.strip()


def _extract_reasoning(text: str) -> str:
    m = re.search(r"REASONING\s*:\s*(.+?)(?=ACTIONS\s*:|$)", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _extract_actions_json(text: str) -> List[dict]:
    """Try to find a JSON array after ACTIONS: label."""
    # First try: ACTIONS: [...]
    m = re.search(r"ACTIONS\s*:\s*(\[.*\])", text, re.DOTALL | re.IGNORECASE)
    if m:
        raw = _clean_json(m.group(1))
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    # Second try: any JSON array in the text
    m = re.search(r"(\[[\s\S]*\])", text)
    if m:
        raw = _clean_json(m.group(1))
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    return []


def _dict_to_action(d: dict):
    action_type = d.get("action_type", "wait")
    cls = ACTION_CLASSES.get(action_type)
    if cls is None:
        return WaitAction()

    def gp(key: str):
        v = d.get(key)
        if isinstance(v, dict):
            return GridPos(float(v.get("x", 0)), float(v.get("y", 0)))
        return None

    if cls == MoveAction:
        return MoveAction(unit_id=d.get("unit_id", ""), target_pos=gp("target_pos"))
    if cls == AttackAction:
        return AttackAction(unit_id=d.get("unit_id", ""), target_unit_id=d.get("target_unit_id", ""))
    if cls == DeployAction:
        return DeployAction(unit_type=d.get("unit_type", ""), position=gp("position"))
    if cls == CallSupportAction:
        return CallSupportAction(
            support_type=d.get("support_type", "artillery"),
            target_pos=gp("target_pos"),
            radius_cells=float(d.get("radius_cells", 10.0)),
        )
    if cls == ScoutAction:
        return ScoutAction(
            unit_id=d.get("unit_id", ""),
            target_area_center=gp("target_area_center"),
            target_area_radius=float(d.get("target_area_radius", 20.0)),
        )
    if cls == DigInAction:
        return DigInAction(unit_id=d.get("unit_id", ""))
    if cls == RetreatAction:
        return RetreatAction(unit_id=d.get("unit_id", ""), direction=gp("direction"))
    return WaitAction(unit_id=d.get("unit_id"))


def parse_llm_output(
    llm_text: str,
    agent_role: str,
    tick: int,
    known_unit_ids: List[str] | None = None,
) -> BattlefieldAction:
    """
    Parse LLM output into a BattlefieldAction.
    Falls back to WaitAction for all known units if parsing fails.
    """
    reasoning = _extract_reasoning(llm_text)
    action_dicts = _extract_actions_json(llm_text)

    actions = []
    for d in action_dicts:
        if not isinstance(d, dict):
            continue
        try:
            a = _dict_to_action(d)
            actions.append(a)
        except Exception as e:
            logger.warning("Failed to parse action %s: %s", d, e)

    if not actions and known_unit_ids:
        logger.warning("No valid actions parsed from LLM output, falling back to wait")
        actions = [WaitAction(unit_id=uid) for uid in known_unit_ids]

    return BattlefieldAction(
        agent_role=agent_role,
        actions=actions,
        reasoning=reasoning,
        timestamp_tick=tick,
    )
