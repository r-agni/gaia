"""
Tests for the proper OpenEnv integration:
  - BattlefieldEnvironment implements openenv.core.Environment ABC
  - Pydantic I/O types are correct subclasses
  - reset() / step() / state return the right types
  - BattlefieldEnvClient is a valid EnvClient subclass
"""
import pytest
from openenv.core import Environment, Action, Observation, State, EnvClient

from battlefield.environment import BattlefieldEnvironment
from battlefield.models import (
    BattlefieldAction,
    BattlefieldCombinedAction,
    BattlefieldObservation,
    BattlefieldFullState,
)
from client.env_client import BattlefieldEnvClient


# ── Type-hierarchy checks ────────────────────────────────────────────────────

class TestTypeHierarchy:
    def test_environment_is_openenv_subclass(self):
        assert issubclass(BattlefieldEnvironment, Environment)

    def test_action_is_openenv_subclass(self):
        assert issubclass(BattlefieldAction, Action)

    def test_combined_action_is_openenv_subclass(self):
        assert issubclass(BattlefieldCombinedAction, Action)

    def test_observation_is_openenv_subclass(self):
        assert issubclass(BattlefieldObservation, Observation)

    def test_full_state_is_openenv_subclass(self):
        assert issubclass(BattlefieldFullState, State)

    def test_client_is_openenv_subclass(self):
        assert issubclass(BattlefieldEnvClient, EnvClient)


# ── Environment.reset() ──────────────────────────────────────────────────────

class TestEnvironmentReset:
    def test_reset_returns_observation(self):
        env = BattlefieldEnvironment()
        obs = env.reset(scenario_id="crossing_at_korzha")
        assert isinstance(obs, BattlefieldObservation)

    def test_reset_tick_is_zero(self):
        env = BattlefieldEnvironment()
        obs = env.reset(scenario_id="crossing_at_korzha")
        assert obs.tick == 0

    def test_reset_has_units(self):
        env = BattlefieldEnvironment()
        obs = env.reset(scenario_id="crossing_at_korzha")
        assert len(obs.own_units) > 0

    def test_reset_done_is_false(self):
        env = BattlefieldEnvironment()
        obs = env.reset(scenario_id="crossing_at_korzha")
        assert obs.done is False

    def test_reset_with_seed(self):
        env1, env2 = BattlefieldEnvironment(), BattlefieldEnvironment()
        obs1 = env1.reset(seed=42)
        obs2 = env2.reset(seed=42)
        assert obs1.own_units_alive == obs2.own_units_alive

    def test_reset_different_seeds_may_differ(self):
        # Not guaranteed to differ but almost always will
        env = BattlefieldEnvironment()
        obs1 = env.reset(seed=1)
        obs2 = env.reset(seed=999)
        # At minimum both return valid observations
        assert isinstance(obs1, BattlefieldObservation)
        assert isinstance(obs2, BattlefieldObservation)


# ── Environment.step() ───────────────────────────────────────────────────────

def _wait_combined():
    return BattlefieldCombinedAction(
        attacker_action=BattlefieldAction(agent_role="attacker", actions=[{"action_type": "wait"}]),
        defender_action=BattlefieldAction(agent_role="defender", actions=[{"action_type": "wait"}]),
    )


class TestEnvironmentStep:
    def test_step_returns_observation(self):
        env = BattlefieldEnvironment()
        env.reset()
        obs = env.step(_wait_combined())
        assert isinstance(obs, BattlefieldObservation)

    def test_step_advances_tick(self):
        env = BattlefieldEnvironment()
        env.reset()
        obs = env.step(_wait_combined())
        assert obs.tick == 1

    def test_step_two_ticks(self):
        env = BattlefieldEnvironment()
        env.reset()
        env.step(_wait_combined())
        obs = env.step(_wait_combined())
        assert obs.tick == 2

    def test_step_attacker_reward_is_float(self):
        env = BattlefieldEnvironment()
        env.reset()
        obs = env.step(_wait_combined())
        assert isinstance(obs.reward, (int, float))

    def test_step_defender_reward_in_metadata(self):
        env = BattlefieldEnvironment()
        env.reset()
        obs = env.step(_wait_combined())
        assert "defender_reward" in obs.metadata
        assert isinstance(obs.metadata["defender_reward"], (int, float))

    def test_step_metadata_has_tick(self):
        env = BattlefieldEnvironment()
        env.reset()
        obs = env.step(_wait_combined())
        assert obs.metadata.get("tick") == 1

    def test_step_done_starts_false(self):
        env = BattlefieldEnvironment()
        env.reset()
        obs = env.step(_wait_combined())
        # One tick should not be terminal
        assert obs.done is False

    def test_step_without_reset_raises(self):
        env = BattlefieldEnvironment()
        with pytest.raises(RuntimeError):
            env.step(_wait_combined())

    def test_step_with_move_action(self):
        env = BattlefieldEnvironment()
        env.reset()
        # Pick first own unit from attacker obs
        obs0 = env.reset()
        unit_id = obs0.own_units[0]["unit_id"]
        action = BattlefieldCombinedAction(
            attacker_action=BattlefieldAction(
                agent_role="attacker",
                actions=[{"action_type": "move", "unit_id": unit_id, "target_pos": {"x": 20, "y": 20}}],
            ),
            defender_action=BattlefieldAction(agent_role="defender", actions=[{"action_type": "wait"}]),
        )
        obs = env.step(action)
        assert isinstance(obs, BattlefieldObservation)


# ── Environment.state ────────────────────────────────────────────────────────

class TestEnvironmentState:
    def test_state_returns_full_state(self):
        env = BattlefieldEnvironment()
        env.reset()
        state = env.state
        assert isinstance(state, BattlefieldFullState)

    def test_state_step_count_is_zero_after_reset(self):
        env = BattlefieldEnvironment()
        env.reset()
        state = env.state
        assert state.step_count == 0

    def test_state_has_units(self):
        env = BattlefieldEnvironment()
        env.reset()
        state = env.state
        assert len(state.units) > 0

    def test_state_has_geo_anchor(self):
        env = BattlefieldEnvironment()
        env.reset()
        state = env.state
        assert "lat0" in state.geo_anchor
        assert "lon0" in state.geo_anchor

    def test_state_tick_advances_after_step(self):
        env = BattlefieldEnvironment()
        env.reset()
        env.step(_wait_combined())
        state = env.state
        assert state.tick == 1

    def test_state_without_reset_returns_empty(self):
        env = BattlefieldEnvironment()
        state = env.state
        assert isinstance(state, BattlefieldFullState)
        assert state.tick == 0


# ── Pydantic model validation ─────────────────────────────────────────────────

class TestPydanticModels:
    def test_action_rejects_unknown_fields(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BattlefieldAction(agent_role="attacker", actions=[], unknown_field="bad")

    def test_combined_action_validates(self):
        action = BattlefieldCombinedAction(
            attacker_action=BattlefieldAction(agent_role="attacker", actions=[]),
            defender_action=BattlefieldAction(agent_role="defender", actions=[]),
        )
        assert action.attacker_action.agent_role == "attacker"

    def test_observation_has_done_field(self):
        obs = BattlefieldObservation()
        assert obs.done is False

    def test_observation_has_reward_field(self):
        obs = BattlefieldObservation()
        assert obs.reward is None

    def test_full_state_has_episode_id(self):
        state = BattlefieldFullState()
        assert state.episode_id is None

    def test_full_state_has_step_count(self):
        state = BattlefieldFullState()
        assert state.step_count == 0


# ── Metadata ─────────────────────────────────────────────────────────────────

class TestEnvironmentMetadata:
    def test_metadata_name(self):
        env = BattlefieldEnvironment()
        meta = env.get_metadata()
        assert meta.name == "BattlefieldEnv"

    def test_metadata_version(self):
        env = BattlefieldEnvironment()
        meta = env.get_metadata()
        assert meta.version == "1.0.0"
