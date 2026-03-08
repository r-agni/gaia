"""
Core data models for the Battlefield RL environment.
All dataclasses used across engine, agents, and server.

Internal engine types use Python @dataclass.
HTTP boundary types (BattlefieldAction, BattlefieldCombinedAction,
BattlefieldObservation, BattlefieldFullState) are Pydantic models that
subclass openenv.core base classes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Literal, Optional, Union

from openenv.core import Action, Observation, State
from pydantic import BaseModel, Field


# ─── Coordinate system ──────────────────────────────────────────────────────
# 1 cell = 100 metres.  All positions are GridPos(x, y) floats.

@dataclass
class GridPos:
    x: float
    y: float

    def distance_to(self, other: "GridPos") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5

    def __add__(self, other: "GridPos") -> "GridPos":
        return GridPos(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "GridPos") -> "GridPos":
        return GridPos(self.x - other.x, self.y - other.y)


@dataclass
class BoundingBox:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def contains(self, pos: GridPos) -> bool:
        return self.x_min <= pos.x <= self.x_max and self.y_min <= pos.y <= self.y_max

    def center(self) -> GridPos:
        return GridPos((self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2)


@dataclass
class GeoAnchor:
    """Maps grid (0,0) to a real WGS84 coordinate for Cesium projection."""
    lat0: float          # latitude of grid origin (y=0)
    lon0: float          # longitude of grid origin (x=0)
    scale_m_per_cell: float = 100.0   # metres per grid cell


# ─── Terrain ────────────────────────────────────────────────────────────────

class TerrainType(IntEnum):
    OPEN     = 0
    FOREST   = 1
    URBAN    = 2
    MOUNTAIN = 3
    RIVER    = 4
    ROAD     = 5


TERRAIN_SPEED_MULT: Dict[TerrainType, float] = {
    TerrainType.OPEN:     1.0,
    TerrainType.FOREST:   0.5,
    TerrainType.URBAN:    0.7,
    TerrainType.MOUNTAIN: 0.3,
    TerrainType.RIVER:    0.1,
    TerrainType.ROAD:     1.3,
}


# ─── Weapon profile ─────────────────────────────────────────────────────────

@dataclass
class WeaponProfile:
    name: str
    min_range_cells: float
    max_range_cells: float
    base_damage: float
    accuracy_at_max_range: float   # 0.0–1.0
    cooldown_ticks: int
    requires_los: bool
    aoe_radius_cells: float        # 0 = direct fire
    ammo_capacity: int             # -1 = unlimited


# ─── Unit templates & instances ─────────────────────────────────────────────

@dataclass
class UnitTemplate:
    unit_type: str
    display_name: str
    max_health: float
    speed_kph: float
    weapon: WeaponProfile
    sensor_range_cells: float
    stealth: float        # 0.0–1.0: reduces enemy effective sensor range against this unit
    armor: float          # fraction of damage absorbed (0.0 = no armour)
    can_fly: bool
    cost: int


class UnitStatus(str):
    ACTIVE     = "active"
    DUG_IN     = "dug_in"
    RETREATING = "retreating"
    DESTROYED  = "destroyed"


@dataclass
class Unit:
    unit_id: str
    template: UnitTemplate
    position: GridPos
    health: float
    ammo: int                      # -1 = unlimited
    status: str                    # UnitStatus constant
    side: Literal["attacker", "defender"]
    cooldown_remaining: int        # ticks until weapon ready
    heading_deg: float             # 0 = north, clockwise
    dug_in: bool = False

    @property
    def unit_type(self) -> str:
        return self.template.unit_type

    @property
    def is_alive(self) -> bool:
        return self.status != UnitStatus.DESTROYED

    @classmethod
    def spawn(cls, template: UnitTemplate, position: GridPos, side: str) -> "Unit":
        return cls(
            unit_id=str(uuid.uuid4())[:8],
            template=template,
            position=position,
            health=template.max_health,
            ammo=template.weapon.ammo_capacity,
            status=UnitStatus.ACTIVE,
            side=side,
            cooldown_remaining=0,
            heading_deg=0.0,
        )


# ─── Scenario config ─────────────────────────────────────────────────────────

@dataclass
class Objective:
    objective_id: str
    name: str
    position: GridPos
    radius_cells: float
    capture_ticks_required: int    # continuous friendly presence ticks to capture
    value: float                   # reward contribution weight


@dataclass
class WinConditions:
    attacker_win: str              # "all_objectives_captured" | "hq_destroyed"
    defender_win: str              # "time_survived" | "attacker_routed"
    attacker_route_threshold: float  # fraction of attacker force destroyed → defender wins
    defender_route_threshold: float  # fraction of defender force destroyed → attacker wins


@dataclass
class UnitSpawn:
    unit_type: str
    position: GridPos
    count: int = 1


@dataclass
class ScenarioConfig:
    scenario_id: str
    name: str
    description: str
    map_size: tuple               # (width_cells, height_cells)
    terrain_seed: int
    attacker_start_zone: BoundingBox
    defender_start_zone: BoundingBox
    objectives: List[Objective]
    attacker_units: List[UnitSpawn]
    defender_units: List[UnitSpawn]
    attacker_resources: int
    defender_resources: int
    max_ticks: int
    win_conditions: WinConditions
    geo_anchor: GeoAnchor


# ─── Actions ─────────────────────────────────────────────────────────────────

@dataclass
class MoveAction:
    action_type: str = "move"
    unit_id: str = ""
    target_pos: Optional[GridPos] = None


@dataclass
class AttackAction:
    action_type: str = "attack"
    unit_id: str = ""
    target_unit_id: str = ""


@dataclass
class DeployAction:
    action_type: str = "deploy"
    unit_type: str = ""
    position: Optional[GridPos] = None


@dataclass
class CallSupportAction:
    action_type: str = "call_support"
    support_type: str = "artillery"    # "artillery" | "airstrike" | "resupply"
    target_pos: Optional[GridPos] = None
    radius_cells: float = 10.0


@dataclass
class ScoutAction:
    action_type: str = "scout"
    unit_id: str = ""
    target_area_center: Optional[GridPos] = None
    target_area_radius: float = 20.0


@dataclass
class DigInAction:
    action_type: str = "dig_in"
    unit_id: str = ""


@dataclass
class RetreatAction:
    action_type: str = "retreat"
    unit_id: str = ""
    direction: Optional[GridPos] = None   # relative vector


@dataclass
class WaitAction:
    action_type: str = "wait"
    unit_id: Optional[str] = None


AnyAction = Union[
    MoveAction, AttackAction, DeployAction, CallSupportAction,
    ScoutAction, DigInAction, RetreatAction, WaitAction
]

ACTION_CLASSES = {
    "move":         MoveAction,
    "attack":       AttackAction,
    "deploy":       DeployAction,
    "call_support": CallSupportAction,
    "scout":        ScoutAction,
    "dig_in":       DigInAction,
    "retreat":      RetreatAction,
    "wait":         WaitAction,
}


@dataclass
class _BattlefieldActionInternal:
    """Internal engine action wrapper (one agent per tick)."""
    agent_role: Literal["attacker", "defender"]
    actions: List[AnyAction]
    reasoning: str = ""            # LLM chain-of-thought (logged, not used by engine)
    timestamp_tick: int = 0


# ─── Observations ────────────────────────────────────────────────────────────

@dataclass
class UnitObservation:
    unit_id: str
    unit_type: str
    position: GridPos
    health: float
    max_health: float
    ammo: int
    status: str
    cooldown_ticks_remaining: int
    heading_deg: float


@dataclass
class EnemyContact:
    contact_id: str
    unit_type: Optional[str]
    last_known_pos: GridPos
    confidence: float              # 1.0 = just sighted; decays 0.1/tick
    ticks_since_sighted: int


@dataclass
class ObjectiveState:
    objective_id: str
    name: str
    position: GridPos
    controlling_side: Optional[str]   # "attacker" | "defender" | "contested" | "neutral"
    capture_progress: float           # 0.0–1.0 for current controller
    ticks_held: int


@dataclass
class TerrainPatch:
    center_pos: GridPos
    terrain_type: str
    elevation: float
    passable: bool


@dataclass
class _BattlefieldObsInternal:
    """Internal engine observation — fog-of-war filtered per agent role."""
    agent_role: Literal["attacker", "defender"]
    tick: int
    max_ticks: int
    own_units: List[UnitObservation]
    enemy_contacts: List[EnemyContact]
    objectives: List[ObjectiveState]
    terrain_patches: List[TerrainPatch]
    resources_remaining: int
    scenario_name: str
    own_units_alive: int
    own_units_destroyed: int
    enemy_contacts_count: int
    tick_progress_pct: float
    recent_events: List[str] = field(default_factory=list)


# ─── OpenEnv Pydantic I/O types (HTTP boundary) ─────────────────────────────
# These inherit from openenv.core base classes so that HTTPEnvServer and
# EnvClient can serialise / deserialise them automatically.


class BattlefieldAction(Action):
    """Single-agent HTTP action submitted via OpenEnv /step."""

    model_config = Action.model_config  # inherit extra="forbid" etc.

    agent_role: Literal["attacker", "defender"] = "attacker"
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    reasoning: str = ""
    timestamp_tick: int = 0


class BattlefieldCombinedAction(Action):
    """Both agents' actions combined for one simultaneous OpenEnv step."""

    model_config = Action.model_config

    attacker_action: BattlefieldAction
    defender_action: BattlefieldAction


class BattlefieldObservation(Observation):
    """Fog-of-war filtered observation returned by OpenEnv /step and /reset."""

    model_config = Observation.model_config

    agent_role: str = ""
    tick: int = 0
    max_ticks: int = 120
    own_units: List[Dict[str, Any]] = Field(default_factory=list)
    enemy_contacts: List[Dict[str, Any]] = Field(default_factory=list)
    objectives: List[Dict[str, Any]] = Field(default_factory=list)
    terrain_patches: List[Dict[str, Any]] = Field(default_factory=list)
    resources_remaining: int = 0
    scenario_name: str = ""
    own_units_alive: int = 0
    own_units_destroyed: int = 0
    enemy_contacts_count: int = 0
    tick_progress_pct: float = 0.0
    recent_events: List[str] = Field(default_factory=list)


class BattlefieldFullState(State):
    """Full (no fog-of-war) state for GET /state — used by Cesium visualization."""

    # State uses extra="allow" so additional fields are fine
    tick: int = 0
    max_ticks: int = 120
    is_terminal: bool = False
    winner: Optional[str] = None
    scenario_id: str = ""
    scenario_name: str = ""
    units: List[Dict[str, Any]] = Field(default_factory=list)
    objectives: List[Dict[str, Any]] = Field(default_factory=list)
    combat_log: List[Dict[str, Any]] = Field(default_factory=list)
    attacker_resources: int = 0
    defender_resources: int = 0
    geo_anchor: Dict[str, Any] = Field(default_factory=dict)


# ─── Engine state ────────────────────────────────────────────────────────────

@dataclass
class ObjectiveCapture:
    objective_id: str
    controlling_side: Optional[str] = None
    capture_progress: float = 0.0
    ticks_held: int = 0
    capture_ticks_required: int = 5


@dataclass
class CombatEvent:
    tick: int
    event_type: str    # "attack" | "unit_destroyed" | "objective_captured" | "support_called"
    attacker_side: str
    description: str
    position: Optional[GridPos] = None


@dataclass
class EngineState:
    scenario: ScenarioConfig
    tick: int
    units: Dict[str, Unit]                      # all units by unit_id (both sides)
    objective_captures: Dict[str, ObjectiveCapture]
    attacker_resources: int
    defender_resources: int
    combat_log: List[CombatEvent]
    is_terminal: bool = False
    winner: Optional[str] = None               # "attacker" | "defender" | "draw"
    attacker_destroyed_count: int = 0
    defender_destroyed_count: int = 0
    attacker_initial_count: int = 0
    defender_initial_count: int = 0
