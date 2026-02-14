"""Weather service — uses Open-Meteo API (free, no API key, Celsius native)."""

from __future__ import annotations

import os

import httpx

from ..config import cfg

# WMO weather code → (Chinese description, emoji)
_WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("晴", "☀️"),
    1: ("大部晴朗", "🌤"),
    2: ("局部多云", "⛅"),
    3: ("多云", "☁️"),
    45: ("雾", "🌫"),
    48: ("雾凇", "🌫"),
    51: ("小毛毛雨", "🌦"),
    53: ("毛毛雨", "🌦"),
    55: ("密集毛毛雨", "🌦"),
    61: ("小雨", "🌧"),
    63: ("中雨", "🌧"),
    65: ("大雨", "🌧"),
    66: ("冻雨（小）", "🌧"),
    67: ("冻雨（大）", "🌧"),
    71: ("小雪", "🌨"),
    73: ("中雪", "🌨"),
    75: ("大雪", "🌨"),
    77: ("雪粒", "🌨"),
    80: ("小阵雨", "🌦"),
    81: ("中阵雨", "🌦"),
    82: ("大阵雨", "🌧"),
    85: ("小阵雪", "🌨"),
    86: ("大阵雪", "🌨"),
    95: ("雷暴", "⛈"),
    96: ("雷暴伴小冰雹", "⛈"),
    99: ("雷暴伴大冰雹", "⛈"),
}


def _wind_description(speed_kmh: float) -> str:
    if speed_kmh < 5:
        return "微风"
    elif speed_kmh < 20:
        return f"风速约{speed_kmh:.0f}公里/时"
    elif speed_kmh < 40:
        return f"较强风，风速{speed_kmh:.0f}公里/时"
    else:
        return f"大风，风速{speed_kmh:.0f}公里/时"


def fetch_weather() -> dict:
    """Fetch current weather + 3-day forecast from Open-Meteo (°C)."""
    base = os.environ.get("WEATHER_API_BASE", "https://api.open-meteo.com")
    url = f"{base}/v1/forecast"
    params: dict[str, str | int | float] = {
        "latitude": cfg.weather_lat,
        "longitude": cfg.weather_lon,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": cfg.timezone,
        "forecast_days": 4,  # today + 3 days
    }

    resp = httpx.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    current = data["current"]
    daily = data["daily"]

    wmo_code = current.get("weather_code", 0)
    condition, icon = _WMO_CODES.get(wmo_code, ("未知", "❓"))

    temp_current = round(current["temperature_2m"])
    temp_high = round(daily["temperature_2m_max"][0])
    temp_low = round(daily["temperature_2m_min"][0])
    wind_speed = current.get("wind_speed_10m", 0)

    summary = (
        f"当前{condition}，气温{temp_current}°C。"
        f"今日最高{temp_high}°C，最低{temp_low}°C。"
        f"{_wind_description(wind_speed)}。"
    )

    # Build 3-day forecast (days 1, 2, 3)
    forecast_days = []
    import datetime
    today = datetime.date.today()
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for i in range(1, 4):
        day_date = today + datetime.timedelta(days=i)
        day_code = daily["weather_code"][i] if i < len(daily["weather_code"]) else 0
        day_cond, day_icon = _WMO_CODES.get(day_code, ("未知", "❓"))
        day_high = round(daily["temperature_2m_max"][i]) if i < len(daily["temperature_2m_max"]) else 0
        day_low = round(daily["temperature_2m_min"][i]) if i < len(daily["temperature_2m_min"]) else 0
        forecast_days.append({
            "label": weekday_names[day_date.weekday()],
            "icon": day_icon,
            "condition": day_cond,
            "high": day_high,
            "low": day_low,
        })

    return {
        "location": cfg.weather_location_name,
        "condition": condition,
        "icon": icon,
        "temp_current": temp_current,
        "temp_high": temp_high,
        "temp_low": temp_low,
        "summary": summary,
        "forecasts": forecast_days,
    }
