"""
GeoGuessRuleAgent -- deterministic fallback agent for demos and testing.

Strategy:
  1. Call terrain_analysis on step 0
  2. Call sun_angle on step 1
  3. Call language_detection on step 2
  4. Then guess using a random popular city with small jitter
"""
from __future__ import annotations

import random

from geoguess.models import GeoGuessAction, GeoGuessObservation

_POPULAR = [
    (48.85, 2.35), (51.5, -0.12), (40.71, -74.0), (35.68, 139.69),
    (28.61, 77.21), (-23.55, -46.63), (19.07, 72.87), (55.75, 37.62),
    (30.04, 31.24), (-33.87, 151.21), (41.01, 28.97), (6.52, 3.38),
    (-1.29, 36.82), (25.2, 55.27), (34.05, -118.24), (39.93, 116.39),
    (-34.61, -58.44), (13.75, 100.52), (1.35, 103.82), (59.94, 30.32),
]

_TOOL_SEQ = ["terrain_analysis", "sun_angle", "language_detection"]


class GeoGuessRuleAgent:
    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def act(self, obs: GeoGuessObservation) -> GeoGuessAction:
        step = obs.step
        steps_remaining = obs.steps_remaining
        guesses_remaining = obs.guesses_remaining

        must_guess = steps_remaining <= 1 or guesses_remaining <= 0

        if not must_guess and step < len(_TOOL_SEQ):
            return GeoGuessAction(
                action_type="tool_call",
                tool_name=_TOOL_SEQ[step],
                reasoning=f"Rule agent: calling {_TOOL_SEQ[step]} at step {step}",
            )

        base_lat, base_lon = self._rng.choice(_POPULAR)
        return GeoGuessAction(
            action_type="guess",
            guess_lat=round(base_lat + self._rng.uniform(-5.0, 5.0), 4),
            guess_lon=round(base_lon + self._rng.uniform(-5.0, 5.0), 4),
            reasoning="Rule agent: random guess near populous area.",
        )

    def reset(self) -> None:
        pass
