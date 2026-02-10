"""
Newsletter Backend — main orchestrator.

This is the entry point that:
1. Fetches content from all services (weather, news, stocks, quotes, etc.)
2. Assembles the payload
3. Calls the email-service via gRPC to render & send the newsletter

Triggered by a cron job (e.g., every morning at 7 AM).
Usage: uv run python -m src.main
"""

from __future__ import annotations

import datetime
import sys
import traceback
import zoneinfo
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import cfg
from .grpc_client import build_request, send_newsletter
from .services import (
    fetch_arxiv_papers,
    fetch_astronomy,
    fetch_exchange_rates,
    fetch_github_trending,
    fetch_hn_stories,
    fetch_news,
    fetch_stocks,
    fetch_weather,
    rank_sections,
)


def _date_string() -> str:
    """Generate a Chinese-formatted date string like '2026年2月8日 · 星期日'."""
    tz = zoneinfo.ZoneInfo(cfg.timezone)
    today = datetime.datetime.now(tz=tz).date()
    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekdays[today.weekday()]
    return f"{today.year}年{today.month}月{today.day}日 · {weekday}"


def _fetch_all() -> dict:
    """Fetch all content sections in parallel."""
    sections: dict[str, object] = {}

    tasks = {
        "weather": fetch_weather,
        "news": fetch_news,
        "stocks": fetch_stocks,
        "hn": fetch_hn_stories,
        "astronomy": fetch_astronomy,
        "github_trending": fetch_github_trending,
        "arxiv": fetch_arxiv_papers,
        "exchange_rates": fetch_exchange_rates,
    }

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}

        for future in as_completed(futures):
            name = futures[future]
            try:
                sections[name] = future.result()
                print(f"  ✅  {name}")
            except Exception as e:
                print(f"  ❌  {name}: {e}")
                traceback.print_exc()
                # Use safe defaults
                if name in ("news", "stocks", "hn", "github_trending", "arxiv", "exchange_rates"):
                    sections[name] = []
                elif name == "astronomy":
                    sections[name] = {"sunrise": "--", "sunset": "--", "day_length": "--"}
                else:
                    sections[name] = {}

    # ── LLM ranking (trim over-fetched lists) ──
    sections = rank_sections(sections)

    return sections


def main() -> None:
    """Main entry point — orchestrate fetching and sending."""
    print("=" * 50)
    print("📰  每日简报 — Newsletter Backend")
    print("=" * 50)
    print()

    date_str = _date_string()
    print(f"📅  {date_str}")
    print(f"📬  Recipient: {cfg.recipient_name} <{cfg.recipient_email}>")
    print()

    # ── Fetch all content ────────────────────
    print("🔄  Fetching content…")
    sections = _fetch_all()
    print()

    # ── Build gRPC request ───────────────────
    print("📦  Building gRPC request…")

    # Merge astronomy data into weather
    weather_data = dict(sections.get("weather", {}))
    astro_data = sections.get("astronomy", {})
    if astro_data:
        weather_data.update({
            "sunrise": astro_data.get("sunrise", ""),
            "sunset": astro_data.get("sunset", ""),
            "day_length": astro_data.get("day_length", ""),
            "golden_hour": astro_data.get("golden_hour", ""),
            "astro_note": astro_data.get("note", ""),
        })

    request = build_request(
        weather=weather_data,
        top_news=sections.get("news", []),
        stocks=sections.get("stocks", []),
        hn_stories=sections.get("hn", []),
        github_trending=sections.get("github_trending", []),
        arxiv_papers=sections.get("arxiv", []),
        exchange_rates=sections.get("exchange_rates", []),
        date_str=date_str,
    )

    # ── Send via gRPC ────────────────────────
    print("📡  Sending to email-service…")
    try:
        response = send_newsletter(request)
        if response.success:
            print("\n🎉  Newsletter sent successfully!")
            print(f"    Message ID: {response.message_id}")
        else:
            print(f"\n❌  Failed to send: {response.error}")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌  gRPC call failed: {e}")
        print("    Is the email-service running? (make dev-server)")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
