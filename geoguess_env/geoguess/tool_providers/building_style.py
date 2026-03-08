"""
Building style tool provider.
Uses HF LLM inference with location metadata; falls back to static lookup.
"""
from __future__ import annotations
import os
import httpx
from ..models import GeoLocation

COUNTRY_STYLE: dict[str, str] = {
    "FR": "Haussmann-era limestone facades, zinc mansard roofs, wrought-iron balconies.",
    "DE": "Post-war concrete blocks mixed with red-brick gabled townhouses.",
    "GB": "Victorian red-brick terraced housing, sash windows, slate roofs.",
    "IT": "Rendered stone buildings, terracotta roof tiles, arched doorways.",
    "ES": "Whitewashed render walls, terracotta tiles, ornate ironwork balconies.",
    "PT": "Azulejo tile facades, Manueline-style ornament, low-rise buildings.",
    "RU": "Stalinist neoclassical high-rises mixed with Soviet panel blocks (khrushchyovkas).",
    "JP": "Mix of reinforced concrete mid-rises, traditional wood-frame; dense urban blocks.",
    "CN": "Modern glass towers; older areas: grey-brick courtyard houses (hutongs).",
    "IN": "Concrete-frame with balconies; older areas: colonial-era brickwork.",
    "BR": "Tropical modernist concrete; favela-style stacked brick in peripheries.",
    "AU": "Single-storey red-brick or weatherboard bungalows, corrugated iron roofs.",
    "ZA": "Low-rise brick/plaster houses, high security walls; townships: corrugated metal.",
    "MX": "Colourful low-rise plaster buildings, flat roofs, enclosed courtyards.",
    "US": "Timber-frame suburban houses with vinyl siding; commercial: glass curtain walls.",
    "CA": "Wood-frame detached houses; cities: glass condo towers, heritage brick warehouses.",
    "EG": "Beige sand-brick concrete multi-storey blocks, flat roofs, unfinished upper floors.",
    "TR": "Concrete apartment blocks; older areas: Ottoman timber-frame with corbelled floors.",
    "GR": "White cuboid buildings with blue-domed churches; mainland: concrete apartments.",
    "AR": "Spanish colonial heritage, flat-roof render; Buenos Aires: French Beaux-Arts.",
    "NG": "Concrete blocks, metal roofs, unfinished upper floors, compound walls.",
    "KE": "Concrete or stone block construction, corrugated iron roofs, open-air markets.",
    "SA": "Modern glass towers; traditional: mud-brick and gypsum decorated facades.",
    "PK": "Painted concrete, carved-wood balconies, Mughal-inspired brick ornament.",
    "VN": "Narrow tube houses (nha ong) in cities, tiled roofs, French colonial remnants.",
    "TH": "Thai-roofed temple structures; urban: modern glass and concrete high-rises.",
    "SE": "Painted timber cottages (Falun red); urban: Jugendstil brick apartment buildings.",
    "PL": "Post-war communist-era panel blocks; old town: Gothic and Renaissance brick.",
}

_SYSTEM = (
    "You are an architectural expert. Describe the predominant building style "
    "of a given location in 2-3 sentences. Focus on: construction materials, "
    "roof style, window type, facade ornament, building height. "
    "Do NOT mention the country or city name."
)


async def resolve(location: GeoLocation, params: dict) -> str:
    hf_key = os.environ.get("HF_API_KEY", "")
    model = os.environ.get("HF_MODEL_ID", "meta-llama/Llama-3.1-8B-Instruct")
    if hf_key:
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                r = await client.post(
                    f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {hf_key}"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM},
                            {"role": "user", "content": (
                                f"Location region: {location.region}, "
                                f"country code: {location.country_code}. "
                                f"Biome: {location.biome}. Describe building style."
                            )},
                        ],
                        "max_tokens": 120,
                        "temperature": 0.3,
                    },
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
    return COUNTRY_STYLE.get(
        location.country_code,
        f"Construction style typical of {location.biome} climate zones: "
        "materials adapted to local conditions, moderate height, practical design.",
    )
