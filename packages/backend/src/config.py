"""Central configuration for the newsletter backend.

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

_ROOT_DIR = Path(__file__).resolve().parents[3]
_CONFIG_PATH = _ROOT_DIR / "newsletter.config.yaml"
_RAW: dict = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))

# Load .env from the project root.
load_dotenv(_ROOT_DIR / ".env")


def _csv(val: str) -> list[str]:
    """Split a comma-separated string into a trimmed list."""
    return [s.strip() for s in val.split(",") if s.strip()]


@dataclass(frozen=True)
class Config:
    """Immutable configuration for the newsletter backend.

    Values are loaded from newsletter.config.yaml at import time.
    Environment variables (via .env or system env) take precedence
    where documented.
    """

    # ── Recipient ────────────────────────────
    recipient_email: str = os.getenv(
        "RECIPIENT_EMAIL", _RAW.get("recipient", {}).get("email", "you@example.com")
    )
    recipient_name: str = os.getenv(
        "RECIPIENT_NAME", _RAW.get("recipient", {}).get("name", "Ziyi")
    )

    # ── Weather (Open-Meteo, no API key needed) ──
    weather_lat: float = float(
        os.getenv("WEATHER_LAT", str(_RAW.get("weather", {}).get("latitude", 37.3688)))
    )
    weather_lon: float = float(
        os.getenv("WEATHER_LON", str(_RAW.get("weather", {}).get("longitude", -122.0363)))
    )
    weather_location_name: str = os.getenv(
        "WEATHER_LOCATION", _RAW.get("weather", {}).get("location", "圣尼维尔，加州")
    )

    # ── News (RSS feeds) ─────────────────────
    news_feeds: list[str] = field(
        default_factory=lambda: _csv(os.getenv("NEWS_FEEDS", ""))
        or _RAW.get("news", {}).get("feeds", [])
    )
    news_max_items: int = int(
        os.getenv("NEWS_MAX_ITEMS", str(_RAW.get("news", {}).get("maxItems", 5)))
    )

    # ── Stocks (yfinance, no API key) ────────
    stock_symbols: list[str] = field(
        default_factory=lambda: _csv(os.getenv("STOCK_SYMBOLS", ""))
        or _RAW.get("stocks", {}).get("symbols", ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"])
    )
    stock_names: dict[str, str] = field(
        default_factory=lambda: _RAW.get("stocks", {}).get("names", {
            "AAPL": "苹果公司",
            "GOOGL": "谷歌母公司",
            "MSFT": "微软公司",
            "TSLA": "特斯拉",
            "NVDA": "英伟达",
        })
    )

    # ── Hacker News ──────────────────────────
    hn_max_stories: int = int(
        os.getenv("HN_MAX_STORIES", str(_RAW.get("hackerNews", {}).get("maxStories", 5)))
    )

    # ── Schedule / Timezone ──────────────────
    timezone: str = os.getenv(
        "TIMEZONE", _RAW.get("schedule", {}).get("timezone", "America/Los_Angeles")
    )

    # ── GitHub Trending ──────────────────────
    github_trending_languages: list[str] = field(
        default_factory=lambda: _RAW.get("githubTrending", {}).get(
            "languages", ["python", "go", "rust"]
        )
    )
    github_trending_max_per_lang: int = int(
        _RAW.get("githubTrending", {}).get("maxPerLanguage", 3)
    )

    # ── arXiv / Gemini ───────────────────────
    arxiv_queries: list[dict] = field(
        default_factory=lambda: _RAW.get("arxiv", {}).get(
            "queries",
            [
                {"query": "cat:cs.CL AND abs:LLM", "label": "LLM", "maxResults": 3},
                {"query": "cat:cs.DC AND abs:HPC", "label": "HPC", "maxResults": 2},
            ],
        )
    )
    gemini_model: str = _RAW.get("arxiv", {}).get("geminiModel", "gemini-2.0-flash")

    # ── LLM Ranking ─────────────────────────
    ranking_enabled: bool = (
        os.getenv("RANKING_ENABLED", str(_raw.get("ranking", {}).get("enabled", False))).lower()
        in ("true", "1", "yes")
    )
    ranking_fetch_multiplier: int = int(
        os.getenv(
            "RANKING_FETCH_MULTIPLIER",
            str(_raw.get("ranking", {}).get("fetchMultiplier", 3)),
        )
    )

    # ── Exchange Rates ───────────────────────
    exchange_rate_pairs: list[str] = field(
        default_factory=lambda: _RAW.get("exchangeRates", {}).get(
            "pairs", ["USD/CNY"]
        )
    )
    exchange_rate_names: dict[str, str] = field(
        default_factory=lambda: _RAW.get("exchangeRates", {}).get(
            "names", {"USD/CNY": "美元/人民币"}
        )
    )

    # ── Todo Tasks (daily.ziyixi.science) ────
    todo_api_user: str = os.getenv("TODO_API_USER", "")
    todo_api_password: str = os.getenv("TODO_API_PASSWORD", "")


# Singleton instance.
cfg = Config()
