"""
Physics: movement, line-of-sight, weapon accuracy, fog-of-war, A* pathfinding.
All operations are on the integer/float grid (1 cell = 100 m).
"""
from __future__ import annotations

import heapq
import math
import random
from typing import List, Optional, Tuple

import numpy as np

from battlefield.models import (
    GridPos,
    TerrainType,
    TERRAIN_SPEED_MULT,
    Unit,
    WeaponProfile,
)


# ─── Line of sight ───────────────────────────────────────────────────────────

def compute_los(
    observer_pos: GridPos,
    target_pos: GridPos,
    observer_elev: float,
    target_elev: float,
    terrain_elevation: np.ndarray,  # shape (height, width), float32
    max_range_cells: float,
) -> bool:
    """
    Bresenham ray cast.  Returns True if observer can see target.
    The ray is blocked if any intermediate cell's terrain elevation
    exceeds the line-of-sight plane between observer and target.
    """
    ox, oy = int(round(observer_pos.x)), int(round(observer_pos.y))
    tx, ty = int(round(target_pos.x)),  int(round(target_pos.y))

    dist = observer_pos.distance_to(target_pos)
    if dist > max_range_cells:
        return False
    if dist < 0.001:
        return True

    # Clamp to terrain bounds
    h, w = terrain_elevation.shape
    if not (0 <= tx < w and 0 <= ty < h):
        return False

    cells = _bresenham_line(ox, oy, tx, ty)
    total = len(cells)
    if total == 0:
        return True

    slope = (target_elev - observer_elev) / max(dist, 1)

    for i, (cx, cy) in enumerate(cells[1:-1], start=1):  # skip endpoints
        if not (0 <= cx < w and 0 <= cy < h):
            continue
        frac = i / total
        los_height_at_cell = observer_elev + slope * (frac * dist)
        if terrain_elevation[cy, cx] > los_height_at_cell:
            return False
    return True


def _bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    cells = []
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        cells.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy; x += sx
        if e2 < dx:
            err += dx; y += sy
    return cells


# ─── Movement & pathfinding ──────────────────────────────────────────────────

def cells_per_tick(unit: Unit, terrain_type: TerrainType) -> float:
    """Maximum distance (cells) the unit can travel in one tick (1 minute)."""
    if unit.template.can_fly:
        mult = 1.0  # flying units ignore ground terrain
    else:
        mult = TERRAIN_SPEED_MULT.get(terrain_type, 1.0)
    return (unit.template.speed_kph * mult) / 60.0


def get_terrain_at(pos: GridPos, terrain_type_map: np.ndarray) -> TerrainType:
    h, w = terrain_type_map.shape
    x, y = max(0, min(int(round(pos.x)), w - 1)), max(0, min(int(round(pos.y)), h - 1))
    return TerrainType(int(terrain_type_map[y, x]))


def astar_path(
    start: GridPos,
    goal: GridPos,
    terrain_type_map: np.ndarray,
    unit: Unit,
    max_cells: float,
) -> GridPos:
    """
    A* pathfinding.  Returns the furthest GridPos the unit can reach toward
    goal within max_cells movement budget.  Uses 8-directional movement.
    Returns start if no movement possible.
    """
    if unit.template.speed_kph == 0:
        return start

    h, w = terrain_type_map.shape
    sx, sy = int(round(start.x)), int(round(start.y))
    gx, gy = int(round(goal.x)),  int(round(goal.y))
    gx = max(0, min(gx, w - 1))
    gy = max(0, min(gy, h - 1))

    # Heuristic: Chebyshev distance
    def heuristic(x: int, y: int) -> float:
        return max(abs(x - gx), abs(y - gy))

    # Movement cost per step (diagonal = sqrt(2) base)
    DIRS = [
        (1, 0), (-1, 0), (0, 1), (0, -1),
        (1, 1), (-1, 1), (1, -1), (-1, -1),
    ]

    open_heap: list = []
    heapq.heappush(open_heap, (0.0, sx, sy))
    came_from: dict[tuple, Optional[tuple]] = {(sx, sy): None}
    g_cost: dict[tuple, float] = {(sx, sy): 0.0}

    while open_heap:
        _, cx, cy = heapq.heappop(open_heap)

        if cx == gx and cy == gy:
            break

        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            step_dist = math.sqrt(dx * dx + dy * dy)
            ttype = TerrainType(int(terrain_type_map[ny, nx]))
            if unit.template.can_fly:
                cost_mult = 1.0
            else:
                cost_mult = 1.0 / max(TERRAIN_SPEED_MULT.get(ttype, 0.01), 0.01)
            step_cost = step_dist * cost_mult
            new_g = g_cost[(cx, cy)] + step_cost

            if new_g > max_cells * 10:  # generous budget ceiling (cost in "terrain units")
                continue

            if (nx, ny) not in g_cost or new_g < g_cost[(nx, ny)]:
                g_cost[(nx, ny)] = new_g
                priority = new_g + heuristic(nx, ny)
                heapq.heappush(open_heap, (priority, nx, ny))
                came_from[(nx, ny)] = (cx, cy)

    # Reconstruct path: use actual goal if reached, else closest explored node
    if (gx, gy) in came_from:
        endpoint = (gx, gy)
    else:
        # Find explored node closest to goal (by Chebyshev distance)
        endpoint = min(came_from.keys(), key=lambda p: max(abs(p[0] - gx), abs(p[1] - gy)))

    path_cells = _reconstruct_path(came_from, (sx, sy), endpoint)

    if len(path_cells) <= 1:
        return start

    # Walk along path, accumulating movement cost, stop at budget
    budget = max_cells
    last_valid = start
    prev = path_cells[0]
    for cell in path_cells[1:]:
        dx = cell[0] - prev[0]
        dy = cell[1] - prev[1]
        step_dist = math.sqrt(dx * dx + dy * dy)
        ttype = TerrainType(int(terrain_type_map[cell[1], cell[0]]))
        if unit.template.can_fly:
            cost_mult = 1.0
        else:
            cost_mult = 1.0 / max(TERRAIN_SPEED_MULT.get(ttype, 0.01), 0.01)
        step_cost = step_dist / cost_mult  # cost in movement distance
        if budget >= step_cost:
            budget -= step_cost
            last_valid = GridPos(float(cell[0]), float(cell[1]))
            prev = cell
        else:
            break
    return last_valid


def _reconstruct_path(
    came_from: dict,
    start: tuple,
    end: tuple,
) -> List[tuple]:
    """Reconstruct A* path from came_from dict. Returns path from start to end."""
    path = []
    current = end
    while current is not None:
        path.append(current)
        current = came_from.get(current)
        if current == start:
            path.append(start)
            break
    path.reverse()
    return path if path and path[0] == start else [start]


# ─── Weapon / combat ─────────────────────────────────────────────────────────

def compute_p_hit(weapon: WeaponProfile, distance_cells: float) -> float:
    """Accuracy at given range using linear interpolation."""
    r = weapon.max_range_cells
    if r <= 0:
        return weapon.accuracy_at_max_range
    frac = min(distance_cells / r, 1.0)
    return weapon.accuracy_at_max_range + (1.0 - weapon.accuracy_at_max_range) * (1.0 - frac)


def resolve_attack(
    attacker: Unit,
    target: Unit,
    terrain_elevation: np.ndarray,
    rng: random.Random,
) -> Tuple[float, bool]:
    """
    Returns (damage_dealt, hit).
    Applies attacker weapon profile + target armor.
    """
    weapon = attacker.template.weapon
    dist = attacker.position.distance_to(target.position)

    # Range check
    if dist < weapon.min_range_cells or dist > weapon.max_range_cells:
        return 0.0, False

    # LOS check (if required)
    if weapon.requires_los:
        obs_elev = _sample_elevation(terrain_elevation, attacker.position)
        tgt_elev = _sample_elevation(terrain_elevation, target.position)
        if not compute_los(
            attacker.position, target.position,
            obs_elev + 2.0, tgt_elev + 2.0,   # +2m for standing observer/target
            terrain_elevation, weapon.max_range_cells,
        ):
            return 0.0, False

    # Accuracy roll
    p_hit = compute_p_hit(weapon, dist)
    if not rng.random() < p_hit:
        return 0.0, False

    # Damage with armor reduction
    armor_reduction = target.template.armor
    if target.dug_in:
        armor_reduction = min(1.0, armor_reduction + 0.4)
    raw_damage = weapon.base_damage
    damage = raw_damage * (1.0 - armor_reduction)
    return damage, True


def resolve_aoe_attack(
    weapon: WeaponProfile,
    target_pos: GridPos,
    all_units: dict,
    terrain_elevation: np.ndarray,
    rng: random.Random,
    side_filter: Optional[str] = None,
) -> dict[str, float]:
    """
    Returns dict of {unit_id: damage} for AoE effects (mortar, artillery, airstrike).
    side_filter: if set, only damage units of that side.
    """
    results = {}
    radius = weapon.aoe_radius_cells
    for uid, unit in all_units.items():
        if not unit.is_alive:
            continue
        if side_filter and unit.side != side_filter:
            continue
        dist = target_pos.distance_to(unit.position)
        if dist <= radius:
            # Damage falls off linearly from center
            falloff = 1.0 - (dist / max(radius, 1.0))
            damage = weapon.base_damage * falloff * (1.0 - unit.template.armor)
            # AoE still has a miss chance scaled by accuracy
            p_hit = compute_p_hit(weapon, target_pos.distance_to(unit.position))
            if rng.random() < p_hit:
                results[uid] = damage
    return results


def _sample_elevation(terrain_elevation: np.ndarray, pos: GridPos) -> float:
    h, w = terrain_elevation.shape
    x = max(0, min(int(round(pos.x)), w - 1))
    y = max(0, min(int(round(pos.y)), h - 1))
    return float(terrain_elevation[y, x])


# ─── Fog of war ──────────────────────────────────────────────────────────────

def compute_visible_enemies(
    friendly_units: list[Unit],
    enemy_units: list[Unit],
    terrain_elevation: np.ndarray,
) -> set[str]:
    """Returns set of enemy unit_ids that are currently visible to any friendly unit."""
    visible = set()
    for friendly in friendly_units:
        if not friendly.is_alive:
            continue
        for enemy in enemy_units:
            if not enemy.is_alive:
                continue
            dist = friendly.position.distance_to(enemy.position)
            # Stealth reduces effective sensor range
            effective_range = friendly.template.sensor_range_cells * (1.0 - enemy.template.stealth)
            if dist > effective_range:
                continue
            # Flying units are always visible within range (they can't hide behind terrain)
            if friendly.template.can_fly or enemy.template.can_fly:
                visible.add(enemy.unit_id)
                continue
            obs_elev = _sample_elevation(terrain_elevation, friendly.position)
            tgt_elev = _sample_elevation(terrain_elevation, enemy.position)
            if compute_los(
                friendly.position, enemy.position,
                obs_elev + 2.0, tgt_elev + 2.0,
                terrain_elevation, effective_range,
            ):
                visible.add(enemy.unit_id)
    return visible
