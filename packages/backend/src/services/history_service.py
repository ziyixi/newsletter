"""
History "On This Day" service — uses Wikipedia's REST API.
"""

from __future__ import annotations

import datetime

import httpx


def fetch_history_events(max_events: int = 4) -> list[dict]:
    """Fetch notable historical events that happened on this day."""
    today = datetime.date.today()
    month = f"{today.month:02d}"
    day = f"{today.day:02d}"

    # Use the English Wikipedia REST API (no auth required)
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{month}/{day}"

    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "NewsletterBot/1.0 (personal newsletter; mailto:bot@example.com)",
                "Accept": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        events = data.get("selected", [])
        results: list[dict] = []

        for event in events[:max_events]:
            year = str(event.get("year", ""))
            text = event.get("text", "")

            # Try to get a Wikipedia link from the first page
            pages = event.get("pages", [])
            wiki_url = ""
            if pages:
                desktop = pages[0].get("content_urls", {}).get("desktop", {})
                wiki_url = desktop.get("page", "")

            results.append(
                {
                    "year": year,
                    "text": text,
                    "url": wiki_url,
                }
            )

        return results

    except Exception as e:
        print(f"⚠️  Failed to fetch history events: {e}")
        return _fallback_events(today)


def _fallback_events(today: datetime.date) -> list[dict]:
    """Return some curated fallback events."""
    return [
        {
            "year": "1587",
            "text": "Mary, Queen of Scots, was executed at Fotheringhay Castle.",
        },
        {
            "year": "1910",
            "text": "The Boy Scouts of America was incorporated.",
        },
    ]
