"""Quotes service — uses ZenQuotes API (free, no API key)."""

from __future__ import annotations

import httpx


def fetch_quote() -> dict:
    """Fetch a random inspirational quote."""
    try:
        resp = httpx.get("https://zenquotes.io/api/random", timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data and isinstance(data, list) and len(data) > 0:
            return {
                "text": data[0].get("q", ""),
                "author": data[0].get("a", "Unknown"),
            }
    except Exception as e:
        print(f"⚠️  Failed to fetch quote: {e}")

    # Fallback
    return {
        "text": "千里之行，始于足下。",
        "author": "老子",
    }
