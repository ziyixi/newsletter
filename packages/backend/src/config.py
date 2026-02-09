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

# ── Load root config ─────────────────────────
_root_dir = Path(__file__).resolve().parents[3]
_config_path = _root_dir / "newsletter.config.yaml"
_raw: dict = yaml.safe_load(_config_path.read_text(encoding="utf-8"))

# Load .env from the project root (where .env actually lives)
load_dotenv(_root_dir / ".env")


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

    # ── GitHub Trending ──────────────────────
    github_trending_languages: list[str] = field(
        default_factory=lambda: _raw.get("githubTrending", {}).get(
            "languages", ["python", "go", "rust"]
        )
    )
    github_trending_max_per_lang: int = int(
        _raw.get("githubTrending", {}).get("maxPerLanguage", 3)
    )

    # ── arXiv / Gemini ───────────────────────
    arxiv_queries: list[dict] = field(
        default_factory=lambda: _raw.get("arxiv", {}).get(
            "queries",
            [
                {"query": "cat:cs.CL AND abs:LLM", "label": "LLM", "maxResults": 3},
                {"query": "cat:cs.DC AND abs:HPC", "label": "HPC", "maxResults": 2},
            ],
        )
    )
    gemini_model: str = _raw.get("arxiv", {}).get("geminiModel", "gemini-2.0-flash")

    # ── Exchange Rates ───────────────────────
    exchange_rate_pairs: list[str] = field(
        default_factory=lambda: _raw.get("exchangeRates", {}).get(
            "pairs", ["USD/CNY"]
        )
    )
    exchange_rate_names: dict[str, str] = field(
        default_factory=lambda: _raw.get("exchangeRates", {}).get(
            "names", {"USD/CNY": "美元/人民币"}
        )
    )


# Singleton
cfg = Config()
