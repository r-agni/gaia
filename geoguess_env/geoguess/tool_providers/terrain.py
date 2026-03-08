"""
Terrain analysis and globe_view tool providers.
Uses Open-Elevation API for elevation + biome lookup.
globe_view uses Google Maps Static API + vision LLM caption.
"""
from __future__ import annotations
import base64
import os
import httpx
from ..models import GeoLocation

_ELEV_API = "https://api.open-elevation.com/api/v1/lookup"

BIOME_DESCRIPTIONS = {
    "temperate_deciduous": "Temperate broadleaf forest. Moderate elevation. Mixed oak, beech, maple canopy.",
    "temperate_grassland": "Open grassland / steppe. Flat to gently rolling. Minimal tree cover.",
    "desert": "Arid desert. Sandy or rocky substrate. Sparse to absent vegetation.",
    "tropical": "Tropical rainforest or monsoon forest. Dense canopy. High humidity apparent.",
    "subtropical": "Subtropical vegetation. Mix of scrubland and open woodland.",
    "boreal": "Boreal taiga forest. Dense conifers (spruce, pine). Flat with wetlands.",
    "tundra": "Arctic or alpine tundra. Treeless. Low mossy vegetation. Rocky outcrops.",
    "mediterranean": "Mediterranean shrubland. Dry hillsides, rocky limestone substrate.",
    "savanna": "Tropical savanna. Scattered acacia trees. Dry grassy ground cover.",
    "urban": "Dense urban area. High building coverage. Road network clearly visible.",
}

VEG_DENSITY = {
    "tropical": "very high", "boreal": "high", "temperate_deciduous": "moderate to high",
    "subtropical": "moderate", "mediterranean": "low to moderate", "savanna": "low",
    "temperate_grassland": "low", "desert": "very low", "tundra": "very low", "urban": "low (urban)",
}


async def resolve_terrain(location: GeoLocation, params: dict) -> str:
    elev_m = await _get_elevation(location.lat, location.lon)
    biome_desc = BIOME_DESCRIPTIONS.get(location.biome, "Mixed vegetation.")
    veg = VEG_DENSITY.get(location.biome, "moderate")
    elev_str = f"{elev_m}m" if elev_m >= 0 else "unknown"
    return (
        f"Elevation: approximately {elev_str} above sea level. "
        f"Vegetation: {biome_desc} "
        f"Vegetation density: {veg}."
    )


async def resolve_globe_view(location: GeoLocation, params: dict) -> str:
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if google_key:
        caption = await _google_maps_caption(location, google_key)
        if caption:
            return caption
    biome_desc = BIOME_DESCRIPTIONS.get(location.biome, "Mixed terrain.")
    pattern = "dense urban grid" if location.biome == "urban" else "scattered rural"
    return f"Aerial view: {biome_desc} Settlement pattern: {pattern}."


async def _get_elevation(lat: float, lon: float) -> int:
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            r = await client.post(_ELEV_API, json={"locations": [{"latitude": lat, "longitude": lon}]})
            r.raise_for_status()
            return int(r.json()["results"][0]["elevation"])
    except Exception:
        return -1


async def _google_maps_caption(location: GeoLocation, api_key: str) -> str:
    hf_key = os.environ.get("HF_API_KEY", "")
    vision_model = os.environ.get("VISION_MODEL_ID", "meta-llama/Llama-3.2-11B-Vision-Instruct")
    if not hf_key:
        return ""
    img_url = (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?center={location.lat},{location.lon}&zoom=14&size=400x400"
        f"&maptype=satellite&key={api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            img_r = await client.get(img_url)
            if img_r.status_code != 200:
                return ""
            img_b64 = base64.b64encode(img_r.content).decode()
            hf_r = await client.post(
                f"https://api-inference.huggingface.co/models/{vision_model}/v1/chat/completions",
                headers={"Authorization": f"Bearer {hf_key}"},
                json={
                    "model": vision_model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                            {"type": "text", "text": (
                                "Describe this satellite image in 2-3 sentences. "
                                "Focus on terrain, vegetation, urban patterns, and water bodies. "
                                "Do NOT mention the country, city name, or any identifying text."
                            )},
                        ],
                    }],
                    "max_tokens": 150,
                },
                timeout=15.0,
            )
            hf_r.raise_for_status()
            return hf_r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""
