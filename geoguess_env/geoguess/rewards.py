"""
GeoGuessr reward functions.

Primary reward: Haversine distance-based exponential decay (GeoGuessr-style).
Bonuses: correct country (+0.10), correct region (+0.05).
Penalty: -0.02 per tool call used (encourages efficiency).
"""
from __future__ import annotations

import math
from typing import List, Optional

import reverse_geocoder as rg  # offline KD-tree, no API key

from .models import GeoLocation

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def distance_score(distance_km: float) -> float:
    """
    GeoGuessr-style exponential decay curve, normalized to [0, 1].

    Reference points:
      0 km    → 1.000
      100 km  → 0.858
      500 km  → 0.458
      1000 km → 0.210
      2000 km → 0.044
      5000 km → 0.000
    """
    if distance_km >= 5000:
        return 0.0
    return round(math.exp(-distance_km / 2000 * 5), 6)


def _reverse_geocode(lat: float, lon: float) -> tuple[str, str]:
    """
    Returns (country_code, region_name) using the offline reverse_geocoder library.
    Falls back to ("", "") on error.
    """
    try:
        results = rg.search([(lat, lon)], verbose=False)
        if results:
            r = results[0]
            return r.get("cc", ""), r.get("admin1", "")
    except Exception:
        pass
    return "", ""


def compute_round_reward(
    guess_lat: float,
    guess_lon: float,
    secret_location: GeoLocation,
    tools_used: int,
) -> tuple[float, float]:
    """
    Compute normalized reward and distance for a single guess.

    Returns:
        (reward: float in [0.0, 1.0], distance_km: float)
    """
    dist_km = haversine_km(guess_lat, guess_lon, secret_location.lat, secret_location.lon)
    base = distance_score(dist_km)

    bonus = 0.0
    guessed_cc, guessed_region = _reverse_geocode(guess_lat, guess_lon)

    if guessed_cc.upper() == secret_location.country_code.upper():
        bonus += 0.10
        if guessed_region and guessed_region.lower() == secret_location.region.lower():
            bonus += 0.05

    tool_penalty = tools_used * 0.02

    total = base + bonus - tool_penalty
    total = max(0.0, min(1.0, total))

    return round(total, 6), round(dist_km, 2)


def compute_episode_reward(round_scores: List[float]) -> float:
    """Average normalized score across all rounds in the episode."""
    if not round_scores:
        return 0.0
    return round(sum(round_scores) / len(round_scores), 6)


def check_country_region(
    guess_lat: float,
    guess_lon: float,
    secret_location: GeoLocation,
) -> tuple[bool, bool]:
    """Returns (correct_country, correct_region)."""
    guessed_cc, guessed_region = _reverse_geocode(guess_lat, guess_lon)
    correct_country = guessed_cc.upper() == secret_location.country_code.upper()
    correct_region = (
        correct_country
        and bool(guessed_region)
        and guessed_region.lower() == secret_location.region.lower()
    )
    return correct_country, correct_region
