"""Tests for scenario configs and catalog."""
import pytest

from battlefield.catalog import get_unit_template, UNIT_CATALOG
from battlefield.scenarios import get_scenario, list_scenarios, SCENARIOS
from battlefield.engine import BattlefieldEngine


class TestCatalog:
    def test_all_unit_types_loadable(self):
        for unit_type in UNIT_CATALOG:
            tmpl = get_unit_template(unit_type)
            assert tmpl.unit_type == unit_type
            assert tmpl.max_health > 0
            assert tmpl.cost > 0

    def test_invalid_unit_type_raises(self):
        with pytest.raises(ValueError):
            get_unit_template("super_laser_tank")


class TestScenarios:
    def test_all_scenarios_loadable(self):
        for sid in SCENARIOS:
            s = get_scenario(sid)
            assert s.scenario_id == sid
            assert len(s.objectives) > 0
            assert len(s.attacker_units) > 0
            assert len(s.defender_units) > 0
            assert s.max_ticks > 0

    def test_invalid_scenario_raises(self):
        with pytest.raises(ValueError):
            get_scenario("battle_of_hogwarts")

    def test_list_scenarios(self):
        result = list_scenarios()
        assert len(result) == len(SCENARIOS)
        for item in result:
            assert "scenario_id" in item
            assert "name" in item

    def test_each_scenario_can_reset(self):
        for sid in SCENARIOS:
            scenario = get_scenario(sid)
            engine = BattlefieldEngine(scenario)
            state = engine.reset()
            assert state.tick == 0
            assert len(state.units) > 0

    def test_geo_anchors_valid(self):
        for sid, s in SCENARIOS.items():
            assert -90 <= s.geo_anchor.lat0 <= 90, f"{sid}: invalid lat"
            assert -180 <= s.geo_anchor.lon0 <= 180, f"{sid}: invalid lon"
            assert s.geo_anchor.scale_m_per_cell > 0
