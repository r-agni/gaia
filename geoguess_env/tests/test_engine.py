"""Tests for BattlefieldEngine: reset, step, win conditions."""
import pytest

from battlefield.engine import BattlefieldEngine
from battlefield.models import (
    AttackAction,
    _BattlefieldActionInternal as BattlefieldAction,
    DeployAction,
    DigInAction,
    GridPos,
    MoveAction,
    WaitAction,
)
from battlefield.scenarios import get_scenario


def _wait_action(role: str, tick: int = 0) -> BattlefieldAction:
    return BattlefieldAction(agent_role=role, actions=[], reasoning="wait", timestamp_tick=tick)


class TestEngineReset:
    def test_reset_produces_state(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()
        assert state.tick == 0
        assert not state.is_terminal
        assert len(state.units) > 0

    def test_reset_spawns_both_sides(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()
        sides = {u.side for u in state.units.values()}
        assert "attacker" in sides
        assert "defender" in sides

    def test_reset_initializes_objectives(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()
        assert len(state.objective_captures) == len(scenario.objectives)
        for cap in state.objective_captures.values():
            assert cap.controlling_side is None
            assert cap.capture_progress == 0.0


class TestEngineStep:
    def test_step_increments_tick(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        engine.reset()
        state, _, _, _ = engine.step(_wait_action("attacker"), _wait_action("defender"))
        assert state.tick == 1

    def test_step_move_action(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()

        # Explicitly pick a light_vehicle (60 kph = 1 cell/tick) to ensure visible movement
        att_units = [u for u in state.units.values() if u.side == "attacker" and u.unit_type == "light_vehicle"]
        assert att_units, "Expected at least one light_vehicle on attacker side"
        u = att_units[0]
        start_x = u.position.x

        move = BattlefieldAction(
            agent_role="attacker",
            actions=[MoveAction(unit_id=u.unit_id, target_pos=GridPos(start_x + 20, u.position.y))],
            reasoning="test move",
        )
        new_state, _, _, _ = engine.step(move, _wait_action("defender"))

        moved_unit = new_state.units[u.unit_id]
        # light_vehicle at 60 kph covers 60/60 = 1 cell/tick — should have advanced
        assert moved_unit.position.x > start_x

    def test_step_deploy_action(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()

        initial_count = sum(1 for u in state.units.values() if u.side == "attacker")
        initial_resources = state.attacker_resources

        deploy = BattlefieldAction(
            agent_role="attacker",
            actions=[DeployAction(unit_type="infantry_squad", position=GridPos(40, 150))],
            reasoning="deploy infantry",
        )
        new_state, _, _, _ = engine.step(deploy, _wait_action("defender"))

        new_count = sum(1 for u in new_state.units.values() if u.side == "attacker")
        assert new_count == initial_count + 1
        assert new_state.attacker_resources == initial_resources - 10  # infantry costs 10

    def test_step_dig_in(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()

        att_units = [u for u in state.units.values() if u.side == "attacker"]
        u = att_units[0]

        dig = BattlefieldAction(
            agent_role="attacker",
            actions=[DigInAction(unit_id=u.unit_id)],
            reasoning="dig in",
        )
        new_state, _, _, _ = engine.step(dig, _wait_action("defender"))
        assert new_state.units[u.unit_id].dug_in is True

    def test_invalid_action_ignored(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        state = engine.reset()

        # Action for non-existent unit
        bad = BattlefieldAction(
            agent_role="attacker",
            actions=[MoveAction(unit_id="NONEXISTENT", target_pos=GridPos(50, 50))],
            reasoning="bad",
        )
        new_state, _, _, _ = engine.step(bad, _wait_action("defender"))
        assert new_state.tick == 1  # should not crash


class TestWinConditions:
    def test_time_limit_ends_game(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        engine.reset()

        for _ in range(scenario.max_ticks):
            state, _, _, done = engine.step(_wait_action("attacker"), _wait_action("defender"))
            if done:
                break

        assert state.is_terminal
        assert state.winner is not None


class TestObservation:
    def test_observation_fog_of_war(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        engine.reset()

        att_obs = engine.get_observation("attacker")
        def_obs = engine.get_observation("defender")

        # Each side sees their own units
        assert len(att_obs.own_units) > 0
        assert len(def_obs.own_units) > 0

        # At tick 0, units are far apart — neither side should see the other
        # (attacker starts x=0-100, defender x=280-500, well beyond sensor range of 15-25)
        assert att_obs.enemy_contacts_count == 0
        assert def_obs.enemy_contacts_count == 0

    def test_observation_tick_matches(self):
        scenario = get_scenario("crossing_at_korzha")
        engine = BattlefieldEngine(scenario)
        engine.reset()
        engine.step(_wait_action("attacker"), _wait_action("defender"))

        obs = engine.get_observation("attacker")
        assert obs.tick == 1
        assert obs.max_ticks == scenario.max_ticks
