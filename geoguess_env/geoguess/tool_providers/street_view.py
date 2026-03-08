"""
Street View tool provider.
Fetches a Google Street View Static image and captions it with a vision LLM.
Falls back to a biome+building style description.
"""
from __future__ import annotations
import base64
import os
import httpx
from ..models import GeoLocation


async def resolve(location: GeoLocation, params: dict) -> str:
    google_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    hf_key = os.environ.get("HF_API_KEY", "")
    vision_model = os.environ.get("VISION_MODEL_ID", "meta-llama/Llama-3.2-11B-Vision-Instruct")

    if google_key and hf_key:
        caption = await _streetview_caption(location, google_key, hf_key, vision_model)
        if caption:
            return caption

    return _fallback_description(location)


async def _streetview_caption(
    location: GeoLocation,
    google_key: str,
    hf_key: str,
    vision_model: str,
) -> str:
    sv_url = (
        f"https://maps.googleapis.com/maps/api/streetview"
        f"?size=400x400&location={location.lat},{location.lon}"
        f"&fov=90&heading=0&pitch=0&key={google_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            img_r = await client.get(sv_url)
            # Google returns a small grey "no imagery" image when unavailable
            if img_r.status_code != 200 or len(img_r.content) < 5000:
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
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                            {"type": "text", "text": (
                                "Describe this street-level image in 3-4 sentences. "
                                "Include: road surface and markings, building architecture and materials, "
                                "vegetation, signage style (but NOT specific text), sky/weather, "
                                "and any vehicles or infrastructure. "
                                "Do NOT name the country, city, or any identifiable location."
                            )},
                        ],
                    }],
                    "max_tokens": 200,
                },
                timeout=18.0,
            )
            hf_r.raise_for_status()
            return hf_r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def _fallback_description(location: GeoLocation) -> str:
    hints = {
        "tropical": "Narrow road, lush green vegetation, red laterite soil visible.",
        "desert": "Dry road, sand-coloured buildings, minimal vegetation.",
        "boreal": "Gravel road through dense conifer forest. Flat terrain.",
        "temperate_deciduous": "Paved road, deciduous trees, moderate density buildings.",
        "urban": "Wide boulevard, multi-story concrete or glass buildings, heavy traffic.",
        "mediterranean": "Limestone or render buildings, terracotta roofs, dry hillside vegetation.",
        "savanna": "Dirt road, acacia trees, single-storey buildings with corrugated metal roofs.",
    }
    return (
        hints.get(location.biome, "A road in an unfamiliar landscape.")
        + " (Street View API not configured — description is approximate.)"
    )
