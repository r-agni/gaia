"""
Reward functions for attacker and defender agents.
Both receive independent reward signals computed after each engine tick.
"""
from __future__ import annotations

from battlefield.models import EngineState


def compute_attacker_reward(
    state: EngineState,
    prev_obj_progress: dict[str, float],
    own_units_lost: int,
    enemy_units_destroyed: int,
    prev_avg_x: float,
    curr_avg_x: float,
) -> float:
    reward = 0.0

    # Shaped: objective capture progress delta
    for obj_id, cap in state.objective_captures.items():
        prev = prev_obj_progress.get(obj_id, 0.0)
        delta = cap.capture_progress - prev
        if cap.controlling_side == "attacker" and delta > 0:
            reward += delta * 5.0   # up to +0.5 per 10% advance

    # Sparse: objective fully captured
    fully_captured = sum(
        1 for cap in state.objective_captures.values()
        if cap.controlling_side == "attacker" and cap.capture_progress >= 1.0
    )
    reward += fully_captured * 20.0

    # Terminal: all objectives captured (win)
    if state.is_terminal and state.winner == "attacker":
        reward += 100.0
    elif state.is_terminal and state.winner == "defender":
        reward -= 50.0

    # Sparse: enemy unit destroyed
    reward += enemy_units_destroyed * 5.0

    # Sparse: own unit lost
    reward -= own_units_lost * 3.0

    # Shaped: time pressure
    reward -= 0.1

    # Shaped: territory advance (average x-position of own units)
    x_delta = curr_avg_x - prev_avg_x
    if x_delta > 0:
        reward += x_delta * 0.02

    return round(reward, 4)


def compute_defender_reward(
    state: EngineState,
    prev_obj_progress: dict[str, float],
    own_units_lost: int,
    enemy_units_destroyed: int,
) -> float:
    reward = 0.0

    # Shaped: objectives held per tick
    for cap in state.objective_captures.values():
        if cap.controlling_side == "defender":
            reward += 1.0

    # Shaped: objectives lost (attacker made progress)
    for obj_id, cap in state.objective_captures.items():
        prev = prev_obj_progress.get(obj_id, 0.0)
        if cap.controlling_side == "attacker" and cap.capture_progress > prev:
            reward -= (cap.capture_progress - prev) * 10.0

    # Sparse: objective fully captured by attacker → defender loss
    for cap in state.objective_captures.values():
        if cap.controlling_side == "attacker" and cap.capture_progress >= 1.0:
            reward -= 25.0

    # Shaped: time survived
    reward += 0.3

    # Sparse: enemy unit destroyed
    reward += enemy_units_destroyed * 5.0

    # Sparse: own unit lost
    reward -= own_units_lost * 2.0

    # Terminal
    if state.is_terminal and state.winner == "defender":
        reward += 80.0
    elif state.is_terminal and state.winner == "attacker":
        reward -= 100.0

    # Shaped: area denial (no attacker within 30 cells of any objective)
    for obj in state.scenario.objectives:
        attacker_near = any(
            u.is_alive and u.side == "attacker" and u.position.distance_to(obj.position) <= 30
            for u in state.units.values()
        )
        if not attacker_near:
            reward += 0.5

    return round(reward, 4)
