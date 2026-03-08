"""
System prompts and observation-to-text conversion for GeoGuessr LLM agents.
"""
from __future__ import annotations

from geoguess.models import AVAILABLE_TOOLS, GeoGuessObservation

SYSTEM_PROMPT = (
    "You are an expert geographer playing GeoGuessr. Your task is to identify the "
    "secret real-world location shown in the scene description below.\n\n"
    "You have a budget of actions per round. Each action is EITHER:\n"
    "  (a) a TOOL CALL to gather more evidence, OR\n"
    "  (b) a GUESS submitting your best lat/lon estimate.\n\n"
    "You want to use as few tools as possible (penalty per tool call) while "
    "guessing as accurately as possible (reward based on distance).\n\n"
    "AVAILABLE TOOLS:\n"
    "  globe_view         - Aerial/satellite imagery description of the location area\n"
    "  street_view        - Street-level imagery description (strongest signal)\n"
    "  terrain_analysis   - Elevation, biome type, vegetation density\n"
    "  weather            - Current weather conditions and seasonal context\n"
    "  sun_angle          - Solar elevation and azimuth (infer latitude and season)\n"
    "  building_style     - Architectural era, materials, roof type, facade ornament\n"
    "  language_detection - Scripts and languages visible on signage\n\n"
    'TOOL CALL FORMAT:\n{"action_type": "tool_call", "tool_name": "<name>", "reasoning": "<your thinking>"}\n\n'
    'GUESS FORMAT:\n{"action_type": "guess", "guess_lat": <float>, "guess_lon": <float>, "reasoning": "<analysis>"}\n\n'
    "STRATEGY:\n"
    "- Start broad: globe_view or terrain_analysis to narrow continent/climate zone\n"
    "- Use sun_angle to estimate latitude band\n"
    "- Use language_detection or building_style to narrow country\n"
    "- Use street_view last -- it gives the strongest clue but costs a step\n"
    "- Submit your guess when sufficiently confident\n"
    "- Always include a detailed reasoning field explaining your geographic logic\n\n"
    "Coordinates: latitude -90 to +90 (N positive), longitude -180 to +180 (E positive)."
)


def observation_to_text(obs: GeoGuessObservation) -> str:
    """Convert a GeoGuessObservation to a human-readable prompt string."""
    return obs.prompt or _build_fallback(obs)


def _build_fallback(obs: GeoGuessObservation) -> str:
    lines = [
        f"GEOGUESS ROUND {obs.round_number + 1}/{obs.total_rounds} -- STEP {obs.step}/{obs.max_steps_per_round}",
        f"GUESSES REMAINING: {obs.guesses_remaining}  |  STEPS REMAINING: {obs.steps_remaining}",
        f"EPISODE SCORE: {obs.episode_score:.3f}",
        "",
        "INITIAL SCENE:",
        obs.initial_scene_description,
    ]
    if obs.tool_results:
        lines += ["", "TOOL RESULTS:"]
        for tr in obs.tool_results:
            lines.append(f"  [{tr['tool_name'].upper()}]: {tr['result']}")
    if obs.guesses:
        lines += ["", "PREVIOUS GUESSES:"]
        for i, g in enumerate(obs.guesses, 1):
            lines.append(
                f"  Guess {i}: ({g['lat']:.4f}, {g['lon']:.4f}) "
                f"-- {g['distance_km']:.1f} km, score {g['score']:.3f}"
            )
    lines += ["", f"AVAILABLE TOOLS: {', '.join(AVAILABLE_TOOLS)}"]
    return "\n".join(lines)
