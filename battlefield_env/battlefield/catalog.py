"""
Unit template catalog.  All available unit types for both sides.
"""
from battlefield.models import UnitTemplate, WeaponProfile

# ─── Weapon profiles ─────────────────────────────────────────────────────────

WEAPONS: dict[str, WeaponProfile] = {
    "rifle": WeaponProfile(
        name="Assault Rifle",
        min_range_cells=0, max_range_cells=5,
        base_damage=15, accuracy_at_max_range=0.4,
        cooldown_ticks=1, requires_los=True,
        aoe_radius_cells=0, ammo_capacity=-1,
    ),
    "sniper_rifle": WeaponProfile(
        name="Sniper Rifle",
        min_range_cells=10, max_range_cells=80,
        base_damage=40, accuracy_at_max_range=0.7,
        cooldown_ticks=2, requires_los=True,
        aoe_radius_cells=0, ammo_capacity=20,
    ),
    "mortar": WeaponProfile(
        name="81mm Mortar",
        min_range_cells=5, max_range_cells=50,
        base_damage=35, accuracy_at_max_range=0.5,
        cooldown_ticks=3, requires_los=False,
        aoe_radius_cells=3, ammo_capacity=30,
    ),
    "autocannon": WeaponProfile(
        name="20mm Autocannon",
        min_range_cells=0, max_range_cells=8,
        base_damage=25, accuracy_at_max_range=0.5,
        cooldown_ticks=1, requires_los=True,
        aoe_radius_cells=0, ammo_capacity=-1,
    ),
    "tank_gun": WeaponProfile(
        name="120mm Tank Gun",
        min_range_cells=0, max_range_cells=15,
        base_damage=120, accuracy_at_max_range=0.6,
        cooldown_ticks=2, requires_los=True,
        aoe_radius_cells=1, ammo_capacity=40,
    ),
    "helicopter_gun": WeaponProfile(
        name="30mm Rotary Cannon",
        min_range_cells=0, max_range_cells=20,
        base_damage=30, accuracy_at_max_range=0.5,
        cooldown_ticks=1, requires_los=True,
        aoe_radius_cells=0, ammo_capacity=-1,
    ),
    "uav_missile": WeaponProfile(
        name="Loitering Munition",
        min_range_cells=0, max_range_cells=10,
        base_damage=80, accuracy_at_max_range=0.8,
        cooldown_ticks=5, requires_los=True,
        aoe_radius_cells=2, ammo_capacity=4,
    ),
    "artillery": WeaponProfile(
        name="155mm Artillery",
        min_range_cells=20, max_range_cells=150,
        base_damage=80, accuracy_at_max_range=0.4,
        cooldown_ticks=4, requires_los=False,
        aoe_radius_cells=8, ammo_capacity=60,
    ),
    "aa_missile": WeaponProfile(
        name="Short-Range SAM",
        min_range_cells=0, max_range_cells=40,
        base_damage=200, accuracy_at_max_range=0.7,
        cooldown_ticks=3, requires_los=True,
        aoe_radius_cells=0, ammo_capacity=8,
    ),
    "mg_emplacement": WeaponProfile(
        name="Fortified MG",
        min_range_cells=0, max_range_cells=6,
        base_damage=20, accuracy_at_max_range=0.6,
        cooldown_ticks=1, requires_los=True,
        aoe_radius_cells=0, ammo_capacity=-1,
    ),
}

# ─── Unit templates ──────────────────────────────────────────────────────────

UNIT_CATALOG: dict[str, UnitTemplate] = {
    "infantry_squad": UnitTemplate(
        unit_type="infantry_squad",
        display_name="Infantry Squad",
        max_health=100, speed_kph=5,
        weapon=WEAPONS["rifle"],
        sensor_range_cells=15, stealth=0.1, armor=0.0,
        can_fly=False, cost=10,
    ),
    "sniper_team": UnitTemplate(
        unit_type="sniper_team",
        display_name="Sniper Team",
        max_health=60, speed_kph=4,
        weapon=WEAPONS["sniper_rifle"],
        sensor_range_cells=30, stealth=0.6, armor=0.0,
        can_fly=False, cost=20,
    ),
    "mortar_team": UnitTemplate(
        unit_type="mortar_team",
        display_name="Mortar Team",
        max_health=80, speed_kph=3,
        weapon=WEAPONS["mortar"],
        sensor_range_cells=10, stealth=0.1, armor=0.0,
        can_fly=False, cost=25,
    ),
    "light_vehicle": UnitTemplate(
        unit_type="light_vehicle",
        display_name="Light Vehicle",
        max_health=200, speed_kph=60,
        weapon=WEAPONS["autocannon"],
        sensor_range_cells=25, stealth=0.0, armor=0.1,
        can_fly=False, cost=30,
    ),
    "armored_vehicle": UnitTemplate(
        unit_type="armored_vehicle",
        display_name="Armored Vehicle",
        max_health=500, speed_kph=40,
        weapon=WEAPONS["tank_gun"],
        sensor_range_cells=20, stealth=0.0, armor=0.5,
        can_fly=False, cost=80,
    ),
    "helicopter": UnitTemplate(
        unit_type="helicopter",
        display_name="Attack Helicopter",
        max_health=300, speed_kph=200,
        weapon=WEAPONS["helicopter_gun"],
        sensor_range_cells=60, stealth=0.0, armor=0.1,
        can_fly=True, cost=100,
    ),
    "uav_drone": UnitTemplate(
        unit_type="uav_drone",
        display_name="UAV Drone",
        max_health=50, speed_kph=120,
        weapon=WEAPONS["uav_missile"],
        sensor_range_cells=80, stealth=0.4, armor=0.0,
        can_fly=True, cost=40,
    ),
    "artillery_battery": UnitTemplate(
        unit_type="artillery_battery",
        display_name="Artillery Battery",
        max_health=400, speed_kph=0,
        weapon=WEAPONS["artillery"],
        sensor_range_cells=5, stealth=0.0, armor=0.2,
        can_fly=False, cost=120,
    ),
    "aa_emplacement": UnitTemplate(
        unit_type="aa_emplacement",
        display_name="AA Emplacement",
        max_health=300, speed_kph=0,
        weapon=WEAPONS["aa_missile"],
        sensor_range_cells=50, stealth=0.0, armor=0.3,
        can_fly=False, cost=90,
    ),
    "fortified_position": UnitTemplate(
        unit_type="fortified_position",
        display_name="Fortified Position",
        max_health=600, speed_kph=0,
        weapon=WEAPONS["mg_emplacement"],
        sensor_range_cells=12, stealth=0.2, armor=0.6,
        can_fly=False, cost=60,
    ),
}


def get_unit_template(unit_type: str) -> UnitTemplate:
    if unit_type not in UNIT_CATALOG:
        raise ValueError(f"Unknown unit type: {unit_type!r}. Valid: {list(UNIT_CATALOG)}")
    return UNIT_CATALOG[unit_type]
