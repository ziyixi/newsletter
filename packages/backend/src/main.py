"""Newsletter Backend — main orchestrator.

Fetches content from all services in parallel, assembles the payload,
and writes it as a JSON file for the email-service to consume.

Architecture:
    Python backend (this) → JSON file → Node.js email-service (render + send)

Usage:
    uv run python -m src.main                          # writes to .cache/newsletter-data.json
    uv run python -m src.main --output /tmp/data.json  # custom output path
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import traceback
import zoneinfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .config import cfg
from .services import (
    fetch_arxiv_papers,
    fetch_astronomy,
    fetch_exchange_rates,
    fetch_github_trending,
    fetch_hn_stories,
    fetch_news,
    fetch_stocks,
    fetch_todo_tasks,
    fetch_weather,
    rank_sections,
)

# ── Constants ────────────────────────────────

_WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / ".cache" / "newsletter-data.json"

# Sections that return a list on failure (vs. empty dict).
_LIST_SECTIONS = frozenset(
    ["news", "stocks", "hn", "github_trending", "arxiv", "exchange_rates", "todo_tasks"]
)

_MAX_WORKERS = 10


def _date_string() -> str:
    """Generate a Chinese-formatted date string.

    Returns:
        A string like '2026年2月8日 · 星期日'.
    """
    tz = zoneinfo.ZoneInfo(cfg.timezone)
    today = datetime.datetime.now(tz=tz).date()
    weekday = _WEEKDAYS_ZH[today.weekday()]
    return f"{today.year}年{today.month}月{today.day}日 · {weekday}"


def _is_skipped(name: str) -> bool:
    """Check if a service should be skipped via SKIP_* env vars.

    Used in integration tests to skip services that rely on Python
    libraries (yfinance, astral, arxiv) rather than HTTP endpoints.
    """
    env_key = f"SKIP_{name.upper()}"
    return os.environ.get(env_key, "").lower() in ("true", "1", "yes")


def _fetch_all() -> dict[str, Any]:
    """Fetch all content sections in parallel.

    Each service is called concurrently. Failures are logged and
    replaced with safe defaults (empty list or empty dict) so the
    newsletter can still render with partial data.

    Services can be skipped via SKIP_* env vars (e.g. SKIP_STOCKS=true).

    Returns:
        A dict mapping section names to their fetched data.
    """
    tasks = {
        "weather": fetch_weather,
        "news": fetch_news,
        "stocks": fetch_stocks,
        "hn": fetch_hn_stories,
        "astronomy": fetch_astronomy,
        "github_trending": fetch_github_trending,
        "arxiv": fetch_arxiv_papers,
        "exchange_rates": fetch_exchange_rates,
        "todo_tasks": fetch_todo_tasks,
    }

    sections: dict[str, Any] = {}

    # Skip services disabled via env vars.
    for name in list(tasks):
        if _is_skipped(name):
            print(f"  ⏭️  {name} (skipped via env)")
            sections[name] = [] if name in _LIST_SECTIONS else {}
            del tasks[name]

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}

        for future in as_completed(futures):
            name = futures[future]
            try:
                sections[name] = future.result()
                print(f"  ✅  {name}")
            except Exception as exc:
                print(f"  ❌  {name}: {exc}")
                traceback.print_exc()
                # Use safe defaults so the newsletter can still render.
                sections[name] = [] if name in _LIST_SECTIONS else {}

    # ── LLM ranking (trim over-fetched lists) ──
    sections = rank_sections(sections)

    return sections


def _merge_astronomy(weather: dict[str, Any], astro: dict[str, Any]) -> dict[str, Any]:
    """Merge astronomy data into the weather dict.

    Args:
        weather: Weather data from fetch_weather().
        astro: Astronomy data from fetch_astronomy().

    Returns:
        A new dict with astronomy fields added to weather.
    """
    merged = dict(weather)
    if astro:
        merged.update({
            "sunrise": astro.get("sunrise", ""),
            "sunset": astro.get("sunset", ""),
            "day_length": astro.get("day_length", ""),
            "golden_hour": astro.get("golden_hour", ""),
            "astro_note": astro.get("note", ""),
        })
    return merged


def _to_camel_case(obj: Any) -> Any:
    """Recursively convert snake_case dict keys to camelCase.

    This ensures the JSON output matches the TypeScript interfaces
    in packages/email-service/emails/types.ts.
    """
    if isinstance(obj, dict):
        return {_snake_to_camel(k): _to_camel_case(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_camel_case(item) for item in obj]
    return obj


def _snake_to_camel(name: str) -> str:
    """Convert a snake_case string to camelCase.

    Already-camelCase strings are returned unchanged.
    """
    if "_" not in name:
        return name
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _assemble_payload(sections: dict[str, Any], date_str: str) -> dict[str, Any]:
    """Assemble the final JSON payload from fetched sections.

    Args:
        sections: Raw section data from _fetch_all().
        date_str: Formatted date string for the newsletter header.

    Returns:
        A camelCase dict ready for JSON serialization.
    """
    weather = _merge_astronomy(
        sections.get("weather", {}),
        sections.get("astronomy", {}),
    )

    payload: dict[str, Any] = {
        "recipientName": cfg.recipient_name,
        "date": date_str,
        "weather": weather,
        "topNews": sections.get("news", []),
        "stocks": sections.get("stocks", []),
        "hnStories": sections.get("hn", []),
        "githubTrending": sections.get("github_trending", []),
        "arxivPapers": sections.get("arxiv", []),
        "exchangeRates": sections.get("exchange_rates", []),
        "todoTasks": sections.get("todo_tasks", []),
    }

    return _to_camel_case(payload)


def main() -> None:
    """Main entry point — fetch all content and write JSON."""
    parser = argparse.ArgumentParser(description="Fetch newsletter data to JSON")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {_DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("📰  每日简报 — Newsletter Backend")
    print("=" * 50)
    print()

    date_str = _date_string()
    print(f"📅  {date_str}")
    print(f"📬  Recipient: {cfg.recipient_name}")
    print()

    # Fetch all content in parallel.
    print("🔄  Fetching content…")
    sections = _fetch_all()
    print()

    # Assemble and write JSON.
    payload = _assemble_payload(sections, date_str)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"💾  Data written to {args.output}")


if __name__ == "__main__":
    main()
