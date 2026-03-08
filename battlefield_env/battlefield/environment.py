"""
BattlefieldEnvironment — proper OpenEnv Environment subclass.

Wraps BattlefieldEngine with the openenv.core.Environment ABC interface so that
HTTPEnvServer can expose it via standard /reset, /step, /state, /schema,
/metadata, /health, and /ws routes.

Action:      BattlefieldCombinedAction  (both agents in one atomic step)
Observation: BattlefieldObservation     (attacker POV; defender reward in metadata)
State:       BattlefieldFullState       (no fog-of-war; used by Cesium visualizer)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from openenv.core import Environment
from openenv.core.env_server.http_server import EnvironmentMetadata

from battlefield.engine import BattlefieldEngine
from battlefield.models import (
    # Pydantic OpenEnv types
    BattlefieldAction,
    BattlefieldCombinedAction,
    BattlefieldObservation,
    BattlefieldFullState,
    # Internal engine types (aliased)
    _BattlefieldActionInternal,
    # Sub-action dataclasses needed for conversion
    ACTION_CLASSES,
    AttackAction,
    CallSupportAction,
    DeployAction,
    DigInAction,
    GridPos,
    MoveAction,
    RetreatAction,
    ScoutAction,
    WaitAction,
)
from battlefield.scenarios import get_scenario


class BattlefieldEnvironment(
    Environment[BattlefieldCombinedAction, BattlefieldObservation, BattlefieldFullState]
):
    """
    OpenEnv-compliant battlefield simulation environment.

    Both attacker and defender actions are submitted in a single
    BattlefieldCombinedAction; the engine resolves them simultaneously.

    Rewards:
        obs.reward                   — attacker scalar reward
        obs.metadata["defender_reward"] — defender scalar reward
        obs.metadata["winner"]       — "attacker" | "defender" | "draw" | None
        obs.metadata["tick"]         — current tick after step
    """

    SUPPORTS_CONCURRENT_SESSIONS = False

    def __init__(self) -> None:
        super().__init__()
        self._engine: Optional[BattlefieldEngine] = None

    # ── OpenEnv ABC ───────────────────────────────────────────────────────────

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        scenario_id: str = "crossing_at_korzha",
        **kwargs: Any,
    ) -> BattlefieldObservation:
        scenario = get_scenario(scenario_id)
        self._engine = BattlefieldEngine(scenario, seed=seed or 0)
        self._engine.reset()
        obs_internal = self._engine.get_observation("attacker")
        result = _obs_to_pydantic(obs_internal)
        result.done = False
        result.reward = None
        return result

    def step(
        self,
        action: BattlefieldCombinedAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> BattlefieldObservation:
        if self._engine is None:
            raise RuntimeError("Call reset() before step()")

        att_internal = _pydantic_action_to_internal(action.attacker_action)
        def_internal = _pydantic_action_to_internal(action.defender_action)

        _, att_r, def_r, done = self._engine.step(att_internal, def_internal)
        obs_internal = self._engine.get_observation("attacker")

        result = _obs_to_pydantic(obs_internal)
        result.done = done
        result.reward = att_r
        result.metadata["defender_reward"] = def_r
        result.metadata["tick"] = self._engine.state.tick
        result.metadata["winner"] = self._engine.state.winner
        return result

    @property
    def state(self) -> BattlefieldFullState:
        return _engine_state_to_pydantic(self._engine)

    def get_metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            name="BattlefieldEnv",
            description=(
                "Two-agent (attacker vs defender) tactical battlefield simulation. "
                "Physics-constrained movement, fog-of-war, and LOS combat on a "
                "100 m/cell grid projected onto a real WGS84 geo-anchor."
            ),
            version="1.0.0",
        )

    def close(self) -> None:
        self._engine = None


# ── Adapter functions ─────────────────────────────────────────────────────────


def _obs_to_pydantic(obs) -> BattlefieldObservation:
    """Convert internal _BattlefieldObsInternal dataclass → Pydantic BattlefieldObservation."""
    def _gp(p: GridPos) -> Dict[str, float]:
        return {"x": round(p.x, 2), "y": round(p.y, 2)}

    return BattlefieldObservation(
        agent_role=obs.agent_role,
        tick=obs.tick,
        max_ticks=obs.max_ticks,
        own_units=[
            {
                "unit_id": u.unit_id,
                "unit_type": u.unit_type,
                "position": _gp(u.position),
                "health": round(u.health, 1),
                "max_health": u.max_health,
                "ammo": u.ammo,
                "status": u.status,
                "cooldown_ticks_remaining": u.cooldown_ticks_remaining,
                "heading_deg": round(u.heading_deg, 1),
            }
            for u in obs.own_units
        ],
        enemy_contacts=[
            {
                "contact_id": c.contact_id,
                "unit_type": c.unit_type,
                "last_known_pos": _gp(c.last_known_pos),
                "confidence": round(c.confidence, 2),
                "ticks_since_sighted": c.ticks_since_sighted,
            }
            for c in obs.enemy_contacts
        ],
        objectives=[
            {
                "objective_id": o.objective_id,
                "name": o.name,
                "position": _gp(o.position),
                "controlling_side": o.controlling_side,
                "capture_progress": round(o.capture_progress, 3),
                "ticks_held": o.ticks_held,
            }
            for o in obs.objectives
        ],
        terrain_patches=[
            {
                "center_pos": _gp(t.center_pos),
                "terrain_type": t.terrain_type,
                "elevation": round(t.elevation, 1),
                "passable": t.passable,
            }
            for t in obs.terrain_patches
        ],
        resources_remaining=obs.resources_remaining,
        scenario_name=obs.scenario_name,
        own_units_alive=obs.own_units_alive,
        own_units_destroyed=obs.own_units_destroyed,
        enemy_contacts_count=obs.enemy_contacts_count,
        tick_progress_pct=obs.tick_progress_pct,
        recent_events=list(obs.recent_events),
    )


def _parse_sub_action(a: Dict[str, Any]):
    """Convert one action dict → internal sub-action dataclass."""
    action_type = a.get("action_type", "wait")
    cls = ACTION_CLASSES.get(action_type)

    def _gp(key: str) -> Optional[GridPos]:
        v = a.get(key)
        return GridPos(v["x"], v["y"]) if v else None

    if cls is MoveAction:
        return MoveAction(unit_id=a.get("unit_id", ""), target_pos=_gp("target_pos"))
    if cls is AttackAction:
        return AttackAction(unit_id=a.get("unit_id", ""), target_unit_id=a.get("target_unit_id", ""))
    if cls is DeployAction:
        return DeployAction(unit_type=a.get("unit_type", ""), position=_gp("position"))
    if cls is CallSupportAction:
        return CallSupportAction(
            support_type=a.get("support_type", "artillery"),
            target_pos=_gp("target_pos"),
            radius_cells=a.get("radius_cells", 10.0),
        )
    if cls is ScoutAction:
        return ScoutAction(
            unit_id=a.get("unit_id", ""),
            target_area_center=_gp("target_area_center"),
            target_area_radius=a.get("target_area_radius", 20.0),
        )
    if cls is DigInAction:
        return DigInAction(unit_id=a.get("unit_id", ""))
    if cls is RetreatAction:
        return RetreatAction(unit_id=a.get("unit_id", ""), direction=_gp("direction"))
    return WaitAction(unit_id=a.get("unit_id"))


def _pydantic_action_to_internal(action: BattlefieldAction) -> _BattlefieldActionInternal:
    """Convert Pydantic BattlefieldAction → internal _BattlefieldActionInternal."""
    return _BattlefieldActionInternal(
        agent_role=action.agent_role,
        actions=[_parse_sub_action(a) for a in action.actions],
        reasoning=action.reasoning,
        timestamp_tick=action.timestamp_tick,
    )


def _engine_state_to_pydantic(engine: Optional[BattlefieldEngine]) -> BattlefieldFullState:
    """Convert BattlefieldEngine state → Pydantic BattlefieldFullState."""
    if engine is None or engine.state is None:
        return BattlefieldFullState()

    s = engine.state
    anchor = s.scenario.geo_anchor

    def _geo(pos: GridPos) -> Dict[str, float]:
        lat = anchor.lat0 + (pos.y * anchor.scale_m_per_cell) / 111320.0
        cos_lat = math.cos(math.radians(anchor.lat0)) or 1e-9
        lon = anchor.lon0 + (pos.x * anchor.scale_m_per_cell) / (111320.0 * cos_lat)
        return {"x": round(pos.x, 2), "y": round(pos.y, 2), "lat": round(lat, 6), "lon": round(lon, 6)}

    units_out: List[Dict[str, Any]] = []
    for u in s.units.values():
        units_out.append({
            "unit_id": u.unit_id,
            "unit_type": u.unit_type,
            "side": u.side,
            "position": _geo(u.position),
            "health": round(u.health, 1),
            "max_health": u.template.max_health,
            "status": u.status,
            "heading_deg": round(u.heading_deg, 1),
            "dug_in": u.dug_in,
        })

    objectives_out: List[Dict[str, Any]] = []
    for obj in s.scenario.objectives:
        cap = s.objective_captures[obj.objective_id]
        objectives_out.append({
            "objective_id": obj.objective_id,
            "name": obj.name,
            "position": _geo(obj.position),
            "controlling_side": cap.controlling_side,
            "capture_progress": round(cap.capture_progress, 3),
            "ticks_held": cap.ticks_held,
        })

    combat_log_out: List[Dict[str, Any]] = [
        {
            "tick": e.tick,
            "event_type": e.event_type,
            "side": e.attacker_side,
            "description": e.description,
            "position": _geo(e.position) if e.position else None,
        }
        for e in s.combat_log
    ]

    return BattlefieldFullState(
        step_count=s.tick,
        tick=s.tick,
        max_ticks=s.scenario.max_ticks,
        is_terminal=s.is_terminal,
        winner=s.winner,
        scenario_id=s.scenario.scenario_id,
        scenario_name=s.scenario.name,
        units=units_out,
        objectives=objectives_out,
        combat_log=combat_log_out,
        attacker_resources=s.attacker_resources,
        defender_resources=s.defender_resources,
        geo_anchor={
            "lat0": anchor.lat0,
            "lon0": anchor.lon0,
            "scale_m_per_cell": anchor.scale_m_per_cell,
        },
    )
