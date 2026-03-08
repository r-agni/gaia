"""
BattlefieldEngine — core simulation tick loop.

Both agents submit their BattlefieldAction before the tick resolves
(simultaneous, not turn-based).  Resolution order per tick:
  1. Validate actions
  2. Movement
  3. Deployments
  4. Attacks (direct fire)
  5. Support calls (AoE)
  6. Dig-in / retreat status updates
  7. Objective capture progress
  8. Remove destroyed units
  9. Check win conditions
"""
from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

import numpy as np

from battlefield.catalog import get_unit_template
from battlefield.models import (
    AnyAction,
    AttackAction,
    _BattlefieldActionInternal as BattlefieldAction,
    _BattlefieldObsInternal as BattlefieldObservation,
    CallSupportAction,
    CombatEvent,
    DeployAction,
    DigInAction,
    EnemyContact,
    EngineState,
    GridPos,
    MoveAction,
    Objective,
    ObjectiveCapture,
    ObjectiveState,
    RetreatAction,
    ScenarioConfig,
    ScoutAction,
    TerrainPatch,
    TerrainType,
    Unit,
    UnitObservation,
    UnitStatus,
    WaitAction,
)
from battlefield.physics import (
    astar_path,
    cells_per_tick,
    compute_visible_enemies,
    get_terrain_at,
    resolve_aoe_attack,
    resolve_attack,
)


def _make_terrain(scenario: ScenarioConfig) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generate procedural terrain from scenario config.
    Returns (elevation[H,W], terrain_type[H,W]).
    In a future iteration these could be loaded from .npy files.
    """
    rng = np.random.RandomState(scenario.terrain_seed)
    w, h = scenario.map_size

    # Elevation: smooth noise via simple averaging passes
    elev = rng.rand(h, w).astype(np.float32) * 50.0  # 0–50 m base
    for _ in range(4):
        elev = (
            elev
            + np.roll(elev, 1, 0) + np.roll(elev, -1, 0)
            + np.roll(elev, 1, 1) + np.roll(elev, -1, 1)
        ) / 5.0

    # Terrain type: default OPEN with features per scenario_id
    ttype = np.zeros((h, w), dtype=np.uint8)  # OPEN by default

    sid = scenario.scenario_id
    if sid == "crossing_at_korzha":
        # River band at x=220-240
        ttype[:, 220:241] = int(TerrainType.RIVER)
        # Bridge corridor: overwrite with ROAD
        ttype[140:161, 228:233] = int(TerrainType.ROAD)
        # Forest patches on attacker side
        rng2 = np.random.RandomState(42)
        for _ in range(8):
            cx, cy = int(rng2.uniform(20, 180)), int(rng2.uniform(40, 260))
            r = int(rng2.uniform(10, 30))
            for fx in range(max(0, cx - r), min(w, cx + r)):
                for fy in range(max(0, cy - r), min(h, cy + r)):
                    if math.sqrt((fx - cx) ** 2 + (fy - cy) ** 2) < r:
                        ttype[fy, fx] = int(TerrainType.FOREST)

    elif sid == "urban_stronghold":
        # Urban center 50-250 x 50-250
        ttype[50:251, 50:251] = int(TerrainType.URBAN)
        # Road spokes
        ttype[145:156, :] = int(TerrainType.ROAD)
        ttype[:, 145:156] = int(TerrainType.ROAD)

    elif sid == "desert_armored_thrust":
        # Rocky ridgelines
        ttype[:, 300:321] = int(TerrainType.MOUNTAIN)
        ttype[:, 550:571] = int(TerrainType.MOUNTAIN)
        elev[:, 300:321] += 40.0
        elev[:, 550:571] += 40.0

    return elev, ttype


class BattlefieldEngine:

    def __init__(self, scenario: ScenarioConfig, seed: int = 0):
        self._scenario = scenario
        self._rng = random.Random(seed)
        self.state: Optional[EngineState] = None

    def reset(self) -> EngineState:
        elev, ttype = _make_terrain(self._scenario)
        units: Dict[str, Unit] = {}

        def spawn_units(spawns, side):
            for spawn in spawns:
                tmpl = get_unit_template(spawn.unit_type)
                for _ in range(spawn.count):
                    u = Unit.spawn(tmpl, GridPos(spawn.position.x, spawn.position.y), side)
                    # Jitter position slightly for multiple spawns of same type
                    u.position = GridPos(
                        spawn.position.x + self._rng.uniform(-2, 2),
                        spawn.position.y + self._rng.uniform(-2, 2),
                    )
                    units[u.unit_id] = u

        spawn_units(self._scenario.attacker_units, "attacker")
        spawn_units(self._scenario.defender_units, "defender")

        obj_captures = {
            obj.objective_id: ObjectiveCapture(
                objective_id=obj.objective_id,
                controlling_side=None,
                capture_progress=0.0,
                ticks_held=0,
                capture_ticks_required=obj.capture_ticks_required,
            )
            for obj in self._scenario.objectives
        }

        att_count = sum(1 for u in units.values() if u.side == "attacker")
        def_count = sum(1 for u in units.values() if u.side == "defender")

        self.state = EngineState(
            scenario=self._scenario,
            tick=0,
            units=units,
            objective_captures=obj_captures,
            attacker_resources=self._scenario.attacker_resources,
            defender_resources=self._scenario.defender_resources,
            combat_log=[],
            is_terminal=False,
            winner=None,
            attacker_destroyed_count=0,
            defender_destroyed_count=0,
            attacker_initial_count=att_count,
            defender_initial_count=def_count,
        )
        self._elev = elev
        self._ttype = ttype
        return self.state

    # ── Public step ──────────────────────────────────────────────────────────

    def step(
        self,
        attacker_action: BattlefieldAction,
        defender_action: BattlefieldAction,
    ) -> Tuple[EngineState, float, float, bool]:
        """
        Process one tick.  Returns (new_state, att_reward, def_reward, done).
        """
        if self.state is None:
            raise RuntimeError("Call reset() before step()")

        s = self.state
        s.tick += 1
        s.combat_log = []

        prev_att_alive = sum(1 for u in s.units.values() if u.side == "attacker" and u.is_alive)
        prev_def_alive = sum(1 for u in s.units.values() if u.side == "defender" and u.is_alive)
        prev_obj_captures = {k: v.capture_progress for k, v in s.objective_captures.items()}
        prev_att_avg_x = self._avg_x("attacker")

        # 1. Validate + collect
        att_acts = self._validate_actions(attacker_action)
        def_acts = self._validate_actions(defender_action)
        scouting_units: set[str] = set()

        # 2. Movement
        for action in att_acts + def_acts:
            if isinstance(action, MoveAction) and action.unit_id and action.target_pos:
                self._do_move(action)
            elif isinstance(action, RetreatAction) and action.unit_id:
                self._do_retreat(action)
            elif isinstance(action, ScoutAction) and action.unit_id:
                scouting_units.add(action.unit_id)

        # 3. Deployments
        for action in att_acts + def_acts:
            if isinstance(action, DeployAction):
                self._do_deploy(action, attacker_action.agent_role if action in att_acts else defender_action.agent_role)

        # 4. Direct attacks (simultaneous damage collection, then apply)
        pending_damage: dict[str, float] = {}
        for action in att_acts + def_acts:
            if isinstance(action, AttackAction):
                if action.unit_id in scouting_units:
                    continue  # scouting units can't attack same tick
                uid = action.unit_id
                tid = action.target_unit_id
                if uid not in s.units or tid not in s.units:
                    continue
                attacker_unit = s.units[uid]
                target_unit = s.units[tid]
                if not attacker_unit.is_alive or not target_unit.is_alive:
                    continue
                if attacker_unit.cooldown_remaining > 0:
                    continue
                dmg, hit = resolve_attack(attacker_unit, target_unit, self._elev, self._rng)
                if hit:
                    pending_damage[tid] = pending_damage.get(tid, 0) + dmg
                    attacker_unit.cooldown_remaining = attacker_unit.template.weapon.cooldown_ticks
                    s.combat_log.append(CombatEvent(
                        tick=s.tick,
                        event_type="attack",
                        attacker_side=attacker_unit.side,
                        description=f"{attacker_unit.unit_type} [{uid}] hits {target_unit.unit_type} [{tid}] for {dmg:.0f} dmg",
                        position=target_unit.position,
                    ))

        # 5. Support calls (AoE)
        for action in att_acts + def_acts:
            if isinstance(action, CallSupportAction):
                role = attacker_action.agent_role if action in att_acts else defender_action.agent_role
                self._do_support(action, role, pending_damage)

        # Apply accumulated damage
        for uid, dmg in pending_damage.items():
            if uid in s.units:
                s.units[uid].health = max(0.0, s.units[uid].health - dmg)

        # 6. Dig-in updates
        for action in att_acts + def_acts:
            if isinstance(action, DigInAction) and action.unit_id in s.units:
                u = s.units[action.unit_id]
                u.dug_in = True
                u.status = UnitStatus.DUG_IN

        # 7. Objective capture
        self._update_objectives()

        # 8. Destroy dead units, decrement cooldowns
        for u in s.units.values():
            if u.health <= 0 and u.is_alive:
                u.status = UnitStatus.DESTROYED
                u.health = 0
                if u.side == "attacker":
                    s.attacker_destroyed_count += 1
                else:
                    s.defender_destroyed_count += 1
                s.combat_log.append(CombatEvent(
                    tick=s.tick,
                    event_type="unit_destroyed",
                    attacker_side=u.side,
                    description=f"{u.unit_type} [{u.unit_id}] ({u.side}) destroyed",
                    position=u.position,
                ))
            if u.cooldown_remaining > 0:
                u.cooldown_remaining -= 1

        # 9. Win conditions
        self._check_win_conditions()

        # 10. Rewards (imported at call time to avoid circular)
        from battlefield.rewards import compute_attacker_reward, compute_defender_reward

        curr_att_alive = sum(1 for u in s.units.values() if u.side == "attacker" and u.is_alive)
        curr_def_alive = sum(1 for u in s.units.values() if u.side == "defender" and u.is_alive)
        att_units_lost = prev_att_alive - curr_att_alive
        def_units_lost = prev_def_alive - curr_def_alive
        curr_att_avg_x = self._avg_x("attacker")

        att_reward = compute_attacker_reward(
            s, prev_obj_captures, att_units_lost, def_units_lost,
            prev_att_avg_x, curr_att_avg_x,
        )
        def_reward = compute_defender_reward(
            s, prev_obj_captures, def_units_lost, att_units_lost,
        )

        return s, att_reward, def_reward, s.is_terminal

    # ── Observation generation ───────────────────────────────────────────────

    def get_observation(self, role: str) -> BattlefieldObservation:
        s = self.state
        friendly = [u for u in s.units.values() if u.side == role and u.is_alive]
        enemy_side = "defender" if role == "attacker" else "attacker"
        enemies = [u for u in s.units.values() if u.side == enemy_side]

        visible_enemy_ids = compute_visible_enemies(friendly, enemies, self._elev)

        own_obs = [
            UnitObservation(
                unit_id=u.unit_id,
                unit_type=u.unit_type,
                position=u.position,
                health=u.health,
                max_health=u.template.max_health,
                ammo=u.ammo,
                status=u.status,
                cooldown_ticks_remaining=u.cooldown_remaining,
                heading_deg=u.heading_deg,
            )
            for u in friendly
        ]

        contacts = []
        for enemy in enemies:
            if enemy.unit_id in visible_enemy_ids:
                contacts.append(EnemyContact(
                    contact_id=enemy.unit_id,
                    unit_type=enemy.unit_type if enemy.is_alive else None,
                    last_known_pos=enemy.position,
                    confidence=1.0,
                    ticks_since_sighted=0,
                ))

        obj_states = []
        for obj in s.scenario.objectives:
            cap = s.objective_captures[obj.objective_id]
            obj_states.append(ObjectiveState(
                objective_id=obj.objective_id,
                name=obj.name,
                position=obj.position,
                controlling_side=cap.controlling_side,
                capture_progress=cap.capture_progress,
                ticks_held=cap.ticks_held,
            ))

        patches = []
        for u in friendly[:5]:  # limit to 5 units for brevity
            ttype = get_terrain_at(u.position, self._ttype)
            patches.append(TerrainPatch(
                center_pos=u.position,
                terrain_type=ttype.name.lower(),
                elevation=float(self._elev[
                    max(0, min(int(round(u.position.y)), self._elev.shape[0] - 1)),
                    max(0, min(int(round(u.position.x)), self._elev.shape[1] - 1)),
                ]),
                passable=ttype != TerrainType.RIVER or u.template.can_fly,
            ))

        resources = s.attacker_resources if role == "attacker" else s.defender_resources
        destroyed_own = s.attacker_destroyed_count if role == "attacker" else s.defender_destroyed_count

        recent = [e.description for e in s.combat_log[-5:]]

        return BattlefieldObservation(
            agent_role=role,
            tick=s.tick,
            max_ticks=s.scenario.max_ticks,
            own_units=own_obs,
            enemy_contacts=contacts,
            objectives=obj_states,
            terrain_patches=patches,
            resources_remaining=resources,
            scenario_name=s.scenario.name,
            own_units_alive=len(friendly),
            own_units_destroyed=destroyed_own,
            enemy_contacts_count=len(contacts),
            tick_progress_pct=round(s.tick / s.scenario.max_ticks * 100, 1),
            recent_events=recent,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _validate_actions(self, action: BattlefieldAction) -> List[AnyAction]:
        """Return only syntactically valid actions for this role."""
        valid = []
        seen_units: set[str] = set()
        for a in action.actions:
            # Each unit may appear at most once (first action wins)
            unit_id = getattr(a, "unit_id", None)
            if unit_id:
                if unit_id in seen_units:
                    continue
                if unit_id not in self.state.units:
                    continue
                if not self.state.units[unit_id].is_alive:
                    continue
                if self.state.units[unit_id].side != action.agent_role:
                    continue
                seen_units.add(unit_id)
            valid.append(a)
        return valid

    def _do_move(self, action: MoveAction) -> None:
        u = self.state.units[action.unit_id]
        ttype = get_terrain_at(u.position, self._ttype)
        budget = cells_per_tick(u, ttype)
        if budget <= 0:
            return
        new_pos = astar_path(u.position, action.target_pos, self._ttype, u, budget)
        if new_pos != u.position:
            dx = new_pos.x - u.position.x
            dy = new_pos.y - u.position.y
            if dx != 0 or dy != 0:
                u.heading_deg = (math.degrees(math.atan2(dx, -dy))) % 360
            u.position = new_pos
            u.dug_in = False
            u.status = UnitStatus.ACTIVE

    def _do_retreat(self, action: RetreatAction) -> None:
        u = self.state.units[action.unit_id]
        if action.direction is None:
            return
        d = action.direction
        norm = max(math.sqrt(d.x ** 2 + d.y ** 2), 0.001)
        ttype = get_terrain_at(u.position, self._ttype)
        budget = cells_per_tick(u, ttype)
        target = GridPos(
            u.position.x + d.x / norm * budget * 3,
            u.position.y + d.y / norm * budget * 3,
        )
        new_pos = astar_path(u.position, target, self._ttype, u, budget)
        u.position = new_pos
        u.status = UnitStatus.RETREATING
        u.dug_in = False

    def _do_deploy(self, action: DeployAction, role: str) -> None:
        s = self.state
        try:
            tmpl = get_unit_template(action.unit_type)
        except ValueError:
            return
        cost = tmpl.cost
        if role == "attacker":
            if s.attacker_resources < cost:
                return
            zone = s.scenario.attacker_start_zone
            s.attacker_resources -= cost
        else:
            if s.defender_resources < cost:
                return
            zone = s.scenario.defender_start_zone
            s.defender_resources -= cost

        pos = action.position or zone.center()
        pos = GridPos(
            max(zone.x_min, min(pos.x, zone.x_max)),
            max(zone.y_min, min(pos.y, zone.y_max)),
        )
        u = Unit.spawn(tmpl, pos, role)
        s.units[u.unit_id] = u
        s.combat_log.append(CombatEvent(
            tick=s.tick, event_type="deploy",
            attacker_side=role,
            description=f"{role} deployed {tmpl.display_name} [{u.unit_id}]",
            position=pos,
        ))

    def _do_support(self, action: CallSupportAction, role: str, pending_damage: dict) -> None:
        s = self.state
        if action.target_pos is None:
            return
        enemy_side = "defender" if role == "attacker" else "attacker"

        from battlefield.catalog import WEAPONS
        if action.support_type == "artillery":
            weapon = WEAPONS["artillery"]
        elif action.support_type == "airstrike":
            weapon = WEAPONS["helicopter_gun"]  # stand-in
        else:
            return  # resupply — no damage

        dmg_map = resolve_aoe_attack(
            weapon, action.target_pos, s.units, self._elev, self._rng, side_filter=enemy_side
        )
        for uid, dmg in dmg_map.items():
            pending_damage[uid] = pending_damage.get(uid, 0) + dmg
        s.combat_log.append(CombatEvent(
            tick=s.tick, event_type="support_called",
            attacker_side=role,
            description=f"{role} called {action.support_type} at ({action.target_pos.x:.0f},{action.target_pos.y:.0f})",
            position=action.target_pos,
        ))

    def _update_objectives(self) -> None:
        s = self.state
        for obj in s.scenario.objectives:
            cap = s.objective_captures[obj.objective_id]
            # Find who is within objective radius
            att_present = any(
                u.is_alive and u.side == "attacker" and u.position.distance_to(obj.position) <= obj.radius_cells
                for u in s.units.values()
            )
            def_present = any(
                u.is_alive and u.side == "defender" and u.position.distance_to(obj.position) <= obj.radius_cells
                for u in s.units.values()
            )

            if att_present and def_present:
                cap.controlling_side = "contested"
                cap.capture_progress = max(0.0, cap.capture_progress - 0.05)
                cap.ticks_held = 0
            elif att_present:
                if cap.controlling_side != "attacker":
                    cap.capture_progress = max(0.0, cap.capture_progress)
                cap.controlling_side = "attacker"
                cap.capture_progress = min(1.0, cap.capture_progress + 1.0 / cap.capture_ticks_required)
                if cap.capture_progress >= 1.0:
                    cap.ticks_held += 1
            elif def_present:
                if cap.controlling_side != "defender":
                    cap.capture_progress = max(0.0, cap.capture_progress)
                cap.controlling_side = "defender"
                if cap.capture_progress < 0.5:
                    cap.capture_progress = min(1.0, cap.capture_progress + 1.0 / cap.capture_ticks_required)
                cap.ticks_held += 1
            else:
                cap.ticks_held = 0

    def _check_win_conditions(self) -> None:
        s = self.state
        wc = s.scenario.win_conditions

        # Time limit
        if s.tick >= s.scenario.max_ticks:
            s.is_terminal = True
            # Count objectives held
            att_objs = sum(
                1 for cap in s.objective_captures.values() if cap.controlling_side == "attacker" and cap.capture_progress >= 1.0
            )
            total_objs = len(s.objective_captures)
            s.winner = "attacker" if att_objs >= total_objs else "defender"
            return

        # Attacker win: all objectives captured
        if wc.attacker_win == "all_objectives_captured":
            all_captured = all(
                cap.controlling_side == "attacker" and cap.capture_progress >= 1.0
                for cap in s.objective_captures.values()
            )
            if all_captured:
                s.is_terminal = True
                s.winner = "attacker"
                return

        # Defender win: time survived (checked via tick limit above)

        # Attacker route: attacker lost too many units
        if s.attacker_initial_count > 0:
            att_alive = sum(1 for u in s.units.values() if u.side == "attacker" and u.is_alive)
            if att_alive / s.attacker_initial_count < (1.0 - wc.attacker_route_threshold):
                s.is_terminal = True
                s.winner = "defender"
                return

        # Defender route: defender lost too many units
        if s.defender_initial_count > 0:
            def_alive = sum(1 for u in s.units.values() if u.side == "defender" and u.is_alive)
            if def_alive / s.defender_initial_count < (1.0 - wc.defender_route_threshold):
                s.is_terminal = True
                s.winner = "attacker"
                return

    def _avg_x(self, side: str) -> float:
        units = [u for u in self.state.units.values() if u.side == side and u.is_alive]
        if not units:
            return 0.0
        return sum(u.position.x for u in units) / len(units)
