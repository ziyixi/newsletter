"""
Central configuration for the newsletter backend.

Reads from the root ``newsletter.config.yaml`` file.
Environment variables override YAML values where noted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env from the backend package root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ── Load root config ─────────────────────────
_root_dir = Path(__file__).resolve().parents[3]
_config_path = _root_dir / "newsletter.config.yaml"
_raw: dict = yaml.safe_load(_config_path.read_text(encoding="utf-8"))


def _csv(val: str) -> list[str]:
    """Split a comma-separated string into a trimmed list."""
    return [s.strip() for s in val.split(",") if s.strip()]


@dataclass(frozen=True)
class Config:
    # ── Recipient ────────────────────────────
    recipient_email: str = os.getenv(
        "RECIPIENT_EMAIL", _raw.get("recipient", {}).get("email", "you@example.com")
    )
    recipient_name: str = os.getenv(
        "RECIPIENT_NAME", _raw.get("recipient", {}).get("name", "子逸")
    )

    # ── gRPC ─────────────────────────────────
    grpc_host: str = os.getenv("GRPC_HOST", "localhost")
    grpc_port: int = int(
        os.getenv("GRPC_PORT", str(_raw.get("grpc", {}).get("port", 50051)))
    )

    @property
    def grpc_target(self) -> str:
        return f"{self.grpc_host}:{self.grpc_port}"

    # ── Weather (Open-Meteo, no API key needed) ──
    weather_lat: float = float(
        os.getenv("WEATHER_LAT", str(_raw.get("weather", {}).get("latitude", 37.3688)))
    )
    weather_lon: float = float(
        os.getenv("WEATHER_LON", str(_raw.get("weather", {}).get("longitude", -122.0363)))
    )
    weather_location_name: str = os.getenv(
        "WEATHER_LOCATION", _raw.get("weather", {}).get("location", "圣尼维尔，加州")
    )

    # ── News (RSS feeds) ─────────────────────
    news_feeds: list[str] = field(
        default_factory=lambda: _csv(
            os.getenv("NEWS_FEEDS", "")
        )
        or _raw.get("news", {}).get("feeds", [])
    )
    news_max_items: int = int(
        os.getenv("NEWS_MAX_ITEMS", str(_raw.get("news", {}).get("maxItems", 5)))
    )

    # ── Stocks (yfinance, no API key) ────────
    stock_symbols: list[str] = field(
        default_factory=lambda: _csv(
            os.getenv("STOCK_SYMBOLS", "")
        )
        or _raw.get("stocks", {}).get("symbols", ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"])
    )
    stock_names: dict[str, str] = field(
        default_factory=lambda: _raw.get("stocks", {}).get("names", {
            "AAPL": "苹果公司",
            "GOOGL": "谷歌母公司",
            "MSFT": "微软公司",
            "TSLA": "特斯拉",
            "NVDA": "英伟达",
        })
    )

    # ── Hacker News ──────────────────────────
    hn_max_stories: int = int(
        os.getenv("HN_MAX_STORIES", str(_raw.get("hackerNews", {}).get("maxStories", 5)))
    )

    # ── Astronomy ────────────────────────────
    timezone: str = os.getenv(
        "TIMEZONE", _raw.get("schedule", {}).get("timezone", "America/Los_Angeles")
    )


# Singleton
cfg = Config()
