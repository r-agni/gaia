"""
Sun angle tool provider.
Uses the astral library (local compute, no API key) for solar position.
"""
from __future__ import annotations
import math
from datetime import datetime, timezone
from ..models import GeoLocation


async def resolve(location: GeoLocation, params: dict) -> str:
    try:
        from astral import LocationInfo
        from astral.sun import sun, elevation, azimuth
        loc = LocationInfo(latitude=location.lat, longitude=location.lon)
        now = datetime.now(tz=timezone.utc)
        elev = elevation(loc.observer, dateandtime=now)
        azim = azimuth(loc.observer, dateandtime=now)
        s = sun(loc.observer, date=now.date())
        sunrise = s["sunrise"].strftime("%H:%M UTC")
        sunset = s["sunset"].strftime("%H:%M UTC")
        day_len_h = (s["sunset"] - s["sunrise"]).seconds / 3600
        lat_hint = _latitude_hint(location.lat, day_len_h)
        return (
            f"Solar elevation: {elev:.1f} degrees (negative = below horizon). "
            f"Solar azimuth: {azim:.1f} degrees. "
            f"Today sunrise: {sunrise}, sunset: {sunset}. "
            f"Day length: {day_len_h:.1f} hours. "
            f"Latitude inference: {lat_hint}."
        )
    except ImportError:
        return _math_fallback(location)
    except Exception as e:
        return f"Sun angle calculation failed: {e}"


def _latitude_hint(lat: float, day_len_h: float) -> str:
    if abs(lat) > 66:
        return "polar region (possible midnight sun or polar night)"
    if abs(lat) > 50:
        return "high latitudes (N/S Europe, Canada, Patagonia)"
    if abs(lat) > 35:
        return "mid latitudes (Central Europe, Japan, NE US, S Australia)"
    if abs(lat) > 20:
        return "subtropical latitudes (Mediterranean, SE US, N India, S Brazil)"
    return "tropical / equatorial zone"


def _math_fallback(location: GeoLocation) -> str:
    now = datetime.now(tz=timezone.utc)
    day_of_year = now.timetuple().tm_yday
    decl = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
    hour_utc = now.hour + now.minute / 60
    solar_hour = hour_utc + location.lon / 15
    hour_angle = 15 * (solar_hour - 12)
    lat_r = math.radians(location.lat)
    dec_r = math.radians(decl)
    ha_r = math.radians(hour_angle)
    sin_elev = (
        math.sin(lat_r) * math.sin(dec_r)
        + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r)
    )
    elev = math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))
    return (
        f"Estimated solar elevation: {elev:.1f} degrees. "
        f"Solar declination today: {decl:.1f} degrees. "
        f"Latitude inference: {_latitude_hint(location.lat, 12)}."
    )
