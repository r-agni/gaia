"""Tests for physics module: LOS, movement, weapons."""
import math
import random

import numpy as np
import pytest

from battlefield.catalog import get_unit_template
from battlefield.models import GridPos, TerrainType, Unit, UnitStatus
from battlefield.physics import (
    astar_path,
    cells_per_tick,
    compute_los,
    compute_p_hit,
    compute_visible_enemies,
    get_terrain_at,
    resolve_attack,
)


def _flat_terrain(h=100, w=100, elev=0.0) -> np.ndarray:
    return np.full((h, w), elev, dtype=np.float32)


def _open_terrain_map(h=100, w=100) -> np.ndarray:
    return np.zeros((h, w), dtype=np.uint8)


def _make_unit(unit_type: str, pos: GridPos, side: str) -> Unit:
    return Unit.spawn(get_unit_template(unit_type), pos, side)


class TestLOS:
    def test_clear_los(self):
        elev = _flat_terrain()
        assert compute_los(GridPos(0, 0), GridPos(10, 10), 2, 2, elev, 50)

    def test_out_of_range(self):
        elev = _flat_terrain()
        assert not compute_los(GridPos(0, 0), GridPos(80, 80), 2, 2, elev, 50)

    def test_blocked_by_hill(self):
        elev = _flat_terrain(elev=0.0)
        # Raise a hill in the middle
        elev[5, 5] = 100.0
        # Observer at (0,0), target at (10,10), hill at (5,5) blocks
        assert not compute_los(GridPos(0, 0), GridPos(10, 10), 2.0, 2.0, elev, 50)

    def test_observer_elevated_sees_over_hill(self):
        elev = _flat_terrain(elev=0.0)
        elev[5, 5] = 30.0
        # Both observer and target elevated above the hill — LOS plane stays above 30m hill
        assert compute_los(GridPos(0, 0), GridPos(10, 10), 40.0, 40.0, elev, 50)


class TestMovement:
    def test_infantry_speed(self):
        tmpl = get_unit_template("infantry_squad")
        u = Unit.spawn(tmpl, GridPos(0, 0), "attacker")
        cpt = cells_per_tick(u, TerrainType.OPEN)
        # 5 kph / 60 min = 0.0833 km/min = 0.833 cells/tick (1 cell = 100m)
        assert abs(cpt - 5 / 60) < 0.01

    def test_vehicle_faster(self):
        light = Unit.spawn(get_unit_template("light_vehicle"), GridPos(0, 0), "attacker")
        inf = Unit.spawn(get_unit_template("infantry_squad"), GridPos(0, 0), "attacker")
        assert cells_per_tick(light, TerrainType.OPEN) > cells_per_tick(inf, TerrainType.OPEN)

    def test_forest_slows_ground_unit(self):
        u = Unit.spawn(get_unit_template("infantry_squad"), GridPos(0, 0), "attacker")
        open_speed = cells_per_tick(u, TerrainType.OPEN)
        forest_speed = cells_per_tick(u, TerrainType.FOREST)
        assert forest_speed < open_speed

    def test_flying_unit_ignores_terrain(self):
        heli = Unit.spawn(get_unit_template("helicopter"), GridPos(0, 0), "attacker")
        assert cells_per_tick(heli, TerrainType.RIVER) == cells_per_tick(heli, TerrainType.OPEN)

    def test_astar_reaches_goal(self):
        tmap = _open_terrain_map()
        u = Unit.spawn(get_unit_template("light_vehicle"), GridPos(0, 0), "attacker")
        # Vehicle moves ~1 cell/tick in open terrain (60kph/60 = 1km/min = 10 cells)
        budget = cells_per_tick(u, TerrainType.OPEN)
        goal = GridPos(5, 0)
        result = astar_path(GridPos(0, 0), goal, tmap, u, budget)
        # Should advance toward goal
        assert result.x > 0

    def test_stationary_unit_doesnt_move(self):
        tmap = _open_terrain_map()
        u = Unit.spawn(get_unit_template("artillery_battery"), GridPos(50, 50), "defender")
        result = astar_path(GridPos(50, 50), GridPos(60, 60), tmap, u, 0)
        assert result.x == 50 and result.y == 50


class TestWeapons:
    def test_p_hit_max_range(self):
        from battlefield.catalog import WEAPONS
        w = WEAPONS["rifle"]
        p = compute_p_hit(w, w.max_range_cells)
        assert abs(p - w.accuracy_at_max_range) < 0.001

    def test_p_hit_zero_range(self):
        from battlefield.catalog import WEAPONS
        w = WEAPONS["rifle"]
        p = compute_p_hit(w, 0)
        assert p > w.accuracy_at_max_range

    def test_attack_out_of_range(self):
        elev = _flat_terrain()
        attacker = _make_unit("infantry_squad", GridPos(0, 0), "attacker")
        target = _make_unit("infantry_squad", GridPos(50, 0), "defender")
        rng = random.Random(42)
        dmg, hit = resolve_attack(attacker, target, elev, rng)
        assert not hit
        assert dmg == 0.0

    def test_attack_in_range_damages(self):
        elev = _flat_terrain()
        attacker = _make_unit("sniper_team", GridPos(0, 0), "attacker")
        target = _make_unit("infantry_squad", GridPos(50, 0), "defender")
        rng = random.Random(0)
        # Try multiple times to get a hit (probabilistic)
        hits = sum(resolve_attack(attacker, target, elev, rng)[1] for _ in range(20))
        assert hits > 0


class TestFogOfWar:
    def test_visible_enemy_in_range(self):
        elev = _flat_terrain()
        friendly = [_make_unit("infantry_squad", GridPos(0, 0), "attacker")]
        enemies = [_make_unit("infantry_squad", GridPos(10, 0), "defender")]
        visible = compute_visible_enemies(friendly, enemies, elev)
        assert enemies[0].unit_id in visible

    def test_enemy_out_of_range_not_visible(self):
        elev = _flat_terrain()
        friendly = [_make_unit("infantry_squad", GridPos(0, 0), "attacker")]
        enemies = [_make_unit("infantry_squad", GridPos(90, 0), "defender")]
        visible = compute_visible_enemies(friendly, enemies, elev)
        assert enemies[0].unit_id not in visible

    def test_stealth_reduces_detection(self):
        elev = _flat_terrain()
        # Sniper has stealth=0.6, so effective sensor range is 15 * (1-0.6) = 6 cells
        friendly = [_make_unit("infantry_squad", GridPos(0, 0), "attacker")]  # sensor 15
        stealth_enemy = [_make_unit("sniper_team", GridPos(10, 0), "defender")]  # stealth 0.6
        visible = compute_visible_enemies(friendly, stealth_enemy, elev)
        # At range 10, effective range 6 → should NOT be visible
        assert stealth_enemy[0].unit_id not in visible
