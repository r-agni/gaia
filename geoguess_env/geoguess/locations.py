"""
Location dataset management for GeoGuessr env.

Datasets are stored as JSONL files under geoguess_env/data/.
Each line is a GeoLocation serialized as JSON.

Bundled datasets:
  - world_cities_5k   : ~5 000 cities, population > 100k, globally balanced
  - natural_wonders   : ~500 curated natural landmarks
  - training_1k       : 1 000 training examples (subset of world_cities_5k)
"""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional

from .models import GeoLocation

_DATA_DIR = Path(__file__).parent.parent / "data"


# ─── Registry ────────────────────────────────────────────────────────────────

_DATASETS: Dict[str, Path] = {
    "world_cities_5k": _DATA_DIR / "world_cities_5k.jsonl",
    "natural_wonders": _DATA_DIR / "natural_wonders.jsonl",
    "training_1k": _DATA_DIR / "training_1k.jsonl",
}

# In-memory cache: dataset_id → list of GeoLocation
_CACHE: Dict[str, List[GeoLocation]] = {}


def list_datasets() -> List[Dict]:
    """Return metadata for all available datasets."""
    result = []
    for dataset_id, path in _DATASETS.items():
        count = 0
        if path.exists():
            with open(path) as f:
                count = sum(1 for _ in f)
        result.append({
            "dataset_id": dataset_id,
            "name": dataset_id.replace("_", " ").title(),
            "path": str(path),
            "count": count,
            "available": path.exists(),
        })
    return result


def get_dataset(dataset_id: str) -> List[GeoLocation]:
    """Load and cache a dataset by ID."""
    if dataset_id in _CACHE:
        return _CACHE[dataset_id]
    path = _DATASETS.get(dataset_id)
    if path is None:
        raise ValueError(f"Unknown dataset: {dataset_id!r}. Available: {list(_DATASETS)}")
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset file not found: {path}\n"
            f"Run: python -m geoguess.scripts.build_datasets to generate it."
        )
    locations = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            locations.append(GeoLocation(**d))
    _CACHE[dataset_id] = locations
    return locations


def sample_locations(
    dataset_id: str,
    n: int,
    seed: int = 0,
    location_id: Optional[str] = None,
) -> List[GeoLocation]:
    """
    Sample n locations from a dataset without replacement, deterministically by seed.
    If location_id is provided, returns exactly that location (used for training replay).
    """
    locations = get_dataset(dataset_id)
    if location_id is not None:
        matches = [loc for loc in locations if loc.location_id == location_id]
        if matches:
            return matches[:1]
        raise ValueError(f"location_id {location_id!r} not found in dataset {dataset_id!r}")
    rng = random.Random(seed)
    pool = list(locations)
    rng.shuffle(pool)
    return pool[:n]


# ─── Scene description generation ────────────────────────────────────────────

# Biome → sparse template phrases (no country/city hints)
_BIOME_TEMPLATES: Dict[str, List[str]] = {
    "temperate_deciduous": [
        "A paved road winds through rolling hills with broadleaf trees.",
        "Green hillsides with mixed deciduous forest. Overcast sky.",
        "A rural lane lined with oak and beech trees. Farmland in the distance.",
    ],
    "temperate_grassland": [
        "Flat open plains stretching to the horizon. Sparse vegetation.",
        "A straight road across a wide grassy steppe. Low shrubs visible.",
        "Rolling grasslands under a partly cloudy sky. No trees in sight.",
    ],
    "desert": [
        "Sand dunes and rocky outcrops. Intense sunlight, almost no vegetation.",
        "Arid scrubland with reddish soil. A few scattered low shrubs.",
        "Flat desert terrain with cracked earth. Mountains visible in the distance.",
    ],
    "tropical": [
        "Dense tropical vegetation. Humid-looking atmosphere and red laterite road.",
        "Lush green jungle lining both sides of a muddy road.",
        "Tropical forest canopy overhead. A river visible through the trees.",
    ],
    "subtropical": [
        "Low scrub vegetation. Bright sun. Eucalyptus-like trees with grey-green foliage.",
        "Mediterranean-style landscape. Dry hills with stone pines and scrubland.",
        "Coastal scrubland. The ocean is visible in the distance.",
    ],
    "boreal": [
        "Dense coniferous forest, mostly spruce and pine. Snow on the ground.",
        "A gravel track through a taiga forest. Sky is pale grey.",
        "Birch and spruce forest. Marshy ground. Flat terrain.",
    ],
    "tundra": [
        "Treeless flat terrain with low mossy vegetation. Cold clear sky.",
        "Arctic-looking landscape. Sparse vegetation, rocky ground, distant ridges.",
    ],
    "mediterranean": [
        "Terraced hillsides with olive trees. Stone walls. Brilliant blue sky.",
        "Rocky Mediterranean coastline. Low scrub vegetation. Limestone buildings.",
    ],
    "savanna": [
        "Acacia trees dotting a dry savanna landscape. Red dirt road.",
        "Open grassland with scattered flat-topped trees. Dry season conditions.",
    ],
    "urban": [
        "A busy city street with multi-story buildings. Signage visible.",
        "An urban intersection. Pedestrians and vehicles. Densely built environment.",
        "High-rise buildings along a wide boulevard. Heavy traffic.",
    ],
}

_DEFAULT_TEMPLATES = [
    "A road running through an unfamiliar landscape.",
    "Open terrain with moderate vegetation.",
    "A settlement visible in the middle distance.",
]


def generate_scene_description(location: GeoLocation, rng: Optional[random.Random] = None) -> str:
    """
    Generate a sparse, location-agnostic initial scene description.
    Used as the 'image caption' presented to the agent at round start.
    In production this is replaced by a real Street View image caption.
    """
    if rng is None:
        rng = random.Random(hash(location.location_id))
    templates = _BIOME_TEMPLATES.get(location.biome, _DEFAULT_TEMPLATES)
    return rng.choice(templates)
