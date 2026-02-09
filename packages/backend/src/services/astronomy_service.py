"""
Astronomy service — sunrise/sunset from Open-Meteo.
Uses the `astral` library for precise sun data.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun

from ..config import cfg


def _format_duration(td: datetime.timedelta) -> str:
    """Format a timedelta as '10时44分'."""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}时{minutes:02d}分"


def fetch_astronomy() -> dict:
    """
    Calculate astronomy data (sunrise, sunset, moon phase, etc.).
    Returns a dict matching the AstronomyData proto message.
    """
    tz = ZoneInfo(cfg.timezone)
    today = datetime.date.today()

    # Astral location
    loc = LocationInfo(
        name=cfg.weather_location_name,
        region="",
        timezone=cfg.timezone,
        latitude=cfg.weather_lat,
        longitude=cfg.weather_lon,
    )

    try:
        s = sun(loc.observer, date=today, tzinfo=tz)

        sunrise_dt = s["sunrise"]
        sunset_dt = s["sunset"]
        day_length = sunset_dt - sunrise_dt

        # Golden hour is roughly 30 minutes before sunset
        golden_hour_dt = sunset_dt - datetime.timedelta(minutes=30)

        return {
            "sunrise": sunrise_dt.strftime("%H:%M"),
            "sunset": sunset_dt.strftime("%H:%M"),
            "day_length": _format_duration(day_length),
            "golden_hour": golden_hour_dt.strftime("%H:%M"),
            "note": "",
        }

    except Exception as e:
        print(f"⚠️  Failed to calculate astronomy data: {e}")
        return {
            "sunrise": "--:--",
            "sunset": "--:--",
            "day_length": "--",
            "golden_hour": "--:--",
            "note": "",
        }
