"""
RuleBasedAgent — deterministic fallback agent for visual demos when no LLM key is set.

Attacker: moves all units toward the nearest uncaptured objective, attacks any
          enemy in range, calls artillery every 15 ticks.
Defender: moves units toward objectives not controlled by defender, attacks any
          enemy in range, digs in when near an objective it holds.
"""
from __future__ import annotations

import math
import random
from typing import Literal

from battlefield.models import (
    _BattlefieldActionInternal as BattlefieldAction,
    _BattlefieldObsInternal as BattlefieldObservation,
    AttackAction,
    CallSupportAction,
    DigInAction,
    GridPos,
    MoveAction,
    WaitAction,
)


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(ax - bx, ay - by)


def _attack_range(unit_type: str) -> float:
    """Approximate max attack range in grid cells."""
    return {
        "infantry_squad": 15,
        "sniper_team": 40,
        "mortar_team": 35,
        "light_vehicle": 20,
        "armored_vehicle": 25,
        "helicopter": 30,
        "uav_drone": 25,
        "artillery_battery": 60,
        "aa_emplacement": 35,
        "fortified_position": 20,
    }.get(unit_type, 15)


class RuleBasedAgent:
    """
    Simple heuristic agent — no API calls required.
    Used for visual demonstrations and as a fallback when HF_API_KEY is absent.
    """

    def __init__(self, role: Literal["attacker", "defender"]) -> None:
        self.role = role

    async def act(self, obs: BattlefieldObservation) -> BattlefieldAction:
        actions = []

        uncaptured = [o for o in obs.objectives if o.controlling_side != self.role]
        held = [o for o in obs.objectives if o.controlling_side == self.role]

        for unit in obs.own_units:
            if unit.status == "destroyed":
                continue

            ux, uy = unit.position.x, unit.position.y
            uid = unit.unit_id

            # 1. Attack nearest enemy in range if weapon is ready
            if unit.cooldown_ticks_remaining == 0 and obs.enemy_contacts:
                nearest = min(
                    obs.enemy_contacts,
                    key=lambda c: _dist(ux, uy, c.last_known_pos.x, c.last_known_pos.y),
                )
                if _dist(ux, uy, nearest.last_known_pos.x, nearest.last_known_pos.y) <= _attack_range(unit.unit_type):
                    actions.append(AttackAction(unit_id=uid, target_unit_id=nearest.contact_id))
                    continue

            # 2. Defender: dig in when near a held objective
            if self.role == "defender" and held and not unit.dug_in:
                nearest_held = min(held, key=lambda o: _dist(ux, uy, o.position.x, o.position.y))
                if _dist(ux, uy, nearest_held.position.x, nearest_held.position.y) <= 8:
                    actions.append(DigInAction(unit_id=uid))
                    continue

            # 3. Move toward nearest uncaptured objective (with jitter so units spread)
            if uncaptured:
                target = min(uncaptured, key=lambda o: _dist(ux, uy, o.position.x, o.position.y))
                jx = (random.random() - 0.5) * 4
                jy = (random.random() - 0.5) * 4
                actions.append(MoveAction(unit_id=uid, target_pos=GridPos(target.position.x + jx, target.position.y + jy)))
            else:
                actions.append(WaitAction(unit_id=uid))

        # 4. Attacker: call artillery every 15 ticks on nearest contact cluster
        if self.role == "attacker" and obs.tick % 15 == 0 and obs.enemy_contacts:
            contact = obs.enemy_contacts[0]
            actions.append(CallSupportAction(
                support_type="artillery",
                target_pos=GridPos(contact.last_known_pos.x, contact.last_known_pos.y),
                radius_cells=12.0,
            ))

        return BattlefieldAction(
            agent_role=self.role,
            actions=actions,
            reasoning=f"Tick {obs.tick}: {self.role} rule agent — {obs.own_units_alive} units alive",
            timestamp_tick=obs.tick,
        )

    def reset(self) -> None:
        pass
