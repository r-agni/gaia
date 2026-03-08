"""
Weather tool provider.
Uses Open-Meteo (free, no API key) to return current weather conditions.
"""
from __future__ import annotations
import httpx
from ..models import GeoLocation

_BASE = "https://api.open-meteo.com/v1/forecast"

WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snowfall", 73: "moderate snowfall", 75: "heavy snowfall",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with hail",
}

SEASONS = {
    "N": {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
          6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"},
    "S": {12: "summer", 1: "summer", 2: "summer", 3: "autumn", 4: "autumn", 5: "autumn",
          6: "winter", 7: "winter", 8: "winter", 9: "spring", 10: "spring", 11: "spring"},
}


async def resolve(location: GeoLocation, params: dict) -> str:
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(_BASE, params={
                "latitude": location.lat,
                "longitude": location.lon,
                "current": "temperature_2m,weathercode,windspeed_10m,relative_humidity_2m",
                "timezone": "auto",
            })
            r.raise_for_status()
            d = r.json()
        curr = d.get("current", {})
        temp = curr.get("temperature_2m", "?")
        wcode = curr.get("weathercode", 0)
        wind = curr.get("windspeed_10m", "?")
        humidity = curr.get("relative_humidity_2m", "?")
        condition = WMO_CODES.get(wcode, f"weather code {wcode}")
        hemi = "S" if location.lat < 0 else "N"
        from datetime import datetime
        month = datetime.now().month
        season = SEASONS[hemi].get(month, "unknown season")
        return (
            f"Current weather: {condition}. Temperature: {temp}C. "
            f"Wind: {wind} km/h. Humidity: {humidity}%. "
            f"Current season in this hemisphere: {season}."
        )
    except Exception as e:
        return f"Weather data temporarily unavailable ({e})."
