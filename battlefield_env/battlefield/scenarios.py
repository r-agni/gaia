"""
Pre-built scenario configurations.
"""
from battlefield.models import (
    BoundingBox,
    GeoAnchor,
    GridPos,
    Objective,
    ScenarioConfig,
    UnitSpawn,
    WinConditions,
)

SCENARIOS: dict[str, ScenarioConfig] = {

    # ── Scenario 1: River crossing ────────────────────────────────────────────
    "crossing_at_korzha": ScenarioConfig(
        scenario_id="crossing_at_korzha",
        name="Crossing at Korzha Bridge",
        description=(
            "Attacker must push across a river bridge chokepoint and capture "
            "a town on the far bank. Defender holds the far side."
        ),
        map_size=(500, 300),
        terrain_seed=1337,
        attacker_start_zone=BoundingBox(0, 50, 100, 250),
        defender_start_zone=BoundingBox(280, 50, 500, 250),
        objectives=[
            Objective(
                objective_id="obj_bridge",
                name="Bridge_Control",
                position=GridPos(230, 150),
                radius_cells=12,
                capture_ticks_required=5,
                value=1.0,
            ),
            Objective(
                objective_id="obj_town",
                name="Town_Center",
                position=GridPos(380, 150),
                radius_cells=15,
                capture_ticks_required=8,
                value=1.5,
            ),
        ],
        attacker_units=[
            UnitSpawn("infantry_squad",  GridPos(50, 120), count=1),
            UnitSpawn("infantry_squad",  GridPos(50, 150), count=1),
            UnitSpawn("infantry_squad",  GridPos(50, 180), count=1),
            UnitSpawn("light_vehicle",   GridPos(60, 140), count=1),
            UnitSpawn("light_vehicle",   GridPos(60, 160), count=1),
            UnitSpawn("mortar_team",     GridPos(30, 150), count=1),
        ],
        defender_units=[
            UnitSpawn("infantry_squad",    GridPos(320, 140), count=1),
            UnitSpawn("infantry_squad",    GridPos(320, 160), count=1),
            UnitSpawn("armored_vehicle",   GridPos(350, 150), count=1),
            UnitSpawn("fortified_position", GridPos(300, 135), count=1),
            UnitSpawn("fortified_position", GridPos(300, 165), count=1),
        ],
        attacker_resources=60,
        defender_resources=40,
        max_ticks=120,
        win_conditions=WinConditions(
            attacker_win="all_objectives_captured",
            defender_win="time_survived",
            attacker_route_threshold=0.70,
            defender_route_threshold=0.70,
        ),
        geo_anchor=GeoAnchor(lat0=47.2, lon0=26.8, scale_m_per_cell=100.0),
    ),

    # ── Scenario 2: Urban stronghold ──────────────────────────────────────────
    "urban_stronghold": ScenarioConfig(
        scenario_id="urban_stronghold",
        name="Urban Stronghold",
        description=(
            "Attacker must clear an urban grid defended by entrenched forces. "
            "Three key buildings must be captured."
        ),
        map_size=(300, 300),
        terrain_seed=2024,
        attacker_start_zone=BoundingBox(0, 0, 300, 50),
        defender_start_zone=BoundingBox(50, 50, 250, 250),
        objectives=[
            Objective(
                objective_id="obj_cityhall",
                name="City_Hall",
                position=GridPos(150, 150),
                radius_cells=10,
                capture_ticks_required=6,
                value=1.5,
            ),
            Objective(
                objective_id="obj_police",
                name="Police_HQ",
                position=GridPos(120, 180),
                radius_cells=8,
                capture_ticks_required=5,
                value=1.0,
            ),
            Objective(
                objective_id="obj_tower",
                name="Broadcast_Tower",
                position=GridPos(180, 120),
                radius_cells=8,
                capture_ticks_required=5,
                value=1.0,
            ),
        ],
        attacker_units=[
            UnitSpawn("infantry_squad", GridPos(50, 20), count=1),
            UnitSpawn("infantry_squad", GridPos(100, 20), count=1),
            UnitSpawn("infantry_squad", GridPos(150, 20), count=1),
            UnitSpawn("infantry_squad", GridPos(200, 20), count=1),
            UnitSpawn("light_vehicle",  GridPos(75, 25), count=1),
            UnitSpawn("light_vehicle",  GridPos(175, 25), count=1),
            UnitSpawn("uav_drone",      GridPos(150, 10), count=1),
        ],
        defender_units=[
            UnitSpawn("infantry_squad",    GridPos(150, 130), count=1),
            UnitSpawn("infantry_squad",    GridPos(120, 160), count=1),
            UnitSpawn("infantry_squad",    GridPos(180, 110), count=1),
            UnitSpawn("fortified_position", GridPos(140, 145), count=1),
            UnitSpawn("fortified_position", GridPos(115, 175), count=1),
            UnitSpawn("fortified_position", GridPos(175, 115), count=1),
            UnitSpawn("sniper_team",       GridPos(150, 200), count=1),
        ],
        attacker_resources=80,
        defender_resources=50,
        max_ticks=180,
        win_conditions=WinConditions(
            attacker_win="all_objectives_captured",
            defender_win="time_survived",
            attacker_route_threshold=0.80,
            defender_route_threshold=0.80,
        ),
        geo_anchor=GeoAnchor(lat0=48.8, lon0=37.5, scale_m_per_cell=100.0),
    ),

    # ── Scenario 3: Desert armored thrust ─────────────────────────────────────
    "desert_armored_thrust": ScenarioConfig(
        scenario_id="desert_armored_thrust",
        name="Desert Armored Thrust",
        description=(
            "Open desert terrain with two rocky ridgelines. Attacker uses "
            "armored vehicles and air assets to seize a supply depot and airfield."
        ),
        map_size=(800, 400),
        terrain_seed=9999,
        attacker_start_zone=BoundingBox(0, 50, 80, 350),
        defender_start_zone=BoundingBox(650, 50, 800, 350),
        objectives=[
            Objective(
                objective_id="obj_depot",
                name="Supply_Depot",
                position=GridPos(680, 200),
                radius_cells=15,
                capture_ticks_required=8,
                value=1.5,
            ),
            Objective(
                objective_id="obj_airfield",
                name="Airfield",
                position=GridPos(730, 250),
                radius_cells=20,
                capture_ticks_required=10,
                value=2.0,
            ),
        ],
        attacker_units=[
            UnitSpawn("armored_vehicle", GridPos(40, 170), count=1),
            UnitSpawn("armored_vehicle", GridPos(40, 200), count=1),
            UnitSpawn("armored_vehicle", GridPos(40, 230), count=1),
            UnitSpawn("helicopter",      GridPos(30, 200), count=1),
            UnitSpawn("light_vehicle",   GridPos(50, 185), count=1),
            UnitSpawn("light_vehicle",   GridPos(50, 215), count=1),
            UnitSpawn("uav_drone",       GridPos(20, 200), count=1),
        ],
        defender_units=[
            UnitSpawn("armored_vehicle",  GridPos(720, 190), count=1),
            UnitSpawn("armored_vehicle",  GridPos(720, 210), count=1),
            UnitSpawn("aa_emplacement",   GridPos(700, 170), count=1),
            UnitSpawn("aa_emplacement",   GridPos(700, 230), count=1),
            UnitSpawn("artillery_battery", GridPos(760, 200), count=1),
            UnitSpawn("infantry_squad",   GridPos(680, 195), count=1),
            UnitSpawn("infantry_squad",   GridPos(730, 245), count=1),
        ],
        attacker_resources=100,
        defender_resources=80,
        max_ticks=200,
        win_conditions=WinConditions(
            attacker_win="all_objectives_captured",
            defender_win="time_survived",
            attacker_route_threshold=0.60,
            defender_route_threshold=0.60,
        ),
        geo_anchor=GeoAnchor(lat0=33.5, lon0=36.0, scale_m_per_cell=100.0),
    ),
}


def get_scenario(scenario_id: str) -> ScenarioConfig:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_id!r}. Valid: {list(SCENARIOS)}")
    return SCENARIOS[scenario_id]


def list_scenarios() -> list[dict]:
    return [
        {
            "scenario_id": s.scenario_id,
            "name": s.name,
            "description": s.description,
            "max_ticks": s.max_ticks,
            "map_size": s.map_size,
        }
        for s in SCENARIOS.values()
    ]
