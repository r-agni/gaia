"""
GeoGuessr environment data models.

Two layers:
  - Internal Python dataclasses used by the engine (never sent over the wire directly)
  - Pydantic models inheriting from openenv.core types for the HTTP/WebSocket boundary
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from openenv.core import Action, Observation, State

# ─── Internal Dataclasses ────────────────────────────────────────────────────


@dataclass
class GeoLocation:
    lat: float
    lon: float
    country_code: str        # ISO 3166-1 alpha-2
    country_name: str
    region: str              # state / province / oblast
    city: Optional[str]
    biome: str               # "temperate_deciduous" | "desert" | "tropical" | ...
    location_id: str


@dataclass
class ToolResult:
    tool_name: str
    invoked_at_step: int
    result_text: str


@dataclass
class GuessRecord:
    lat: float
    lon: float
    reasoning: str
    distance_km: float       # filled by engine after guess
    score: float             # normalized [0, 1]
    correct_country: bool
    correct_region: bool
    step: int


@dataclass
class RoundState:
    round_number: int        # 0-indexed
    location: GeoLocation
    initial_scene_description: str
    step: int = 0
    tool_results: List[ToolResult] = field(default_factory=list)
    guesses: List[GuessRecord] = field(default_factory=list)
    is_terminal: bool = False
    round_score: float = 0.0
    tools_budget_used: int = 0
    oversight_flags: List[str] = field(default_factory=list)


@dataclass
class GeoGuessEngineState:
    dataset_id: str
    episode_id: str
    current_round: int       # 0-indexed
    total_rounds: int
    max_steps_per_round: int
    max_guesses_per_round: int
    rounds: List[RoundState] = field(default_factory=list)
    episode_score: float = 0.0
    is_terminal: bool = False
    training_mode: bool = False
    training_episode: int = 0


# Available tool names (the agent can call any of these)
AVAILABLE_TOOLS: List[str] = [
    "globe_view",
    "street_view",
    "terrain_analysis",
    "weather",
    "sun_angle",
    "building_style",
    "language_detection",
]


# ─── OpenEnv Pydantic Types (HTTP boundary) ──────────────────────────────────


class GeoGuessAction(Action):
    """
    Single step from the agent. Either a tool call OR a guess.
    Exactly one semantic branch must be populated per action_type.
    """
    action_type: Literal["tool_call", "guess"] = "guess"
    # Tool call fields
    tool_name: Optional[str] = None
    tool_params: Dict[str, Any] = {}
    # Guess fields
    guess_lat: Optional[float] = None
    guess_lon: Optional[float] = None
    # Always required
    reasoning: str = ""


class GeoGuessObservation(Observation):
    """What the agent sees each step — secret location is NOT included."""
    round_number: int = 0
    total_rounds: int = 5
    step: int = 0
    max_steps_per_round: int = 7
    initial_scene_description: str = ""
    tool_results: List[Dict[str, Any]] = []
    guesses: List[Dict[str, Any]] = []
    steps_remaining: int = 7
    guesses_remaining: int = 2
    episode_score: float = 0.0
    available_tools: List[str] = AVAILABLE_TOOLS
    prompt: str = ""         # full natural-language prompt for the LLM


class GeoGuessFullState(State):
    """
    Full (non-hidden) state returned by GET /state and broadcast over WS.
    Secret revealed as None during active round, populated after round ends.
    """
    episode_id: str = ""
    current_round: int = 0
    total_rounds: int = 5
    is_terminal: bool = False
    episode_score: float = 0.0
    # Secret (None = still hidden)
    secret_lat: Optional[float] = None
    secret_lon: Optional[float] = None
    secret_country: str = "??"
    secret_region: str = "??"
    # Agent's best/latest guess
    current_guess_lat: Optional[float] = None
    current_guess_lon: Optional[float] = None
    guesses: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    round_history: List[Dict[str, Any]] = []
    training_mode: bool = False
    episode: int = 0
    # Oversight agent flags for the current round
    oversight_flags: List[str] = []
    oversight_summary: Dict[str, Any] = {}
