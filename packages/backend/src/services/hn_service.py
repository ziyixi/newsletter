"""
Hacker News service — uses the official HN Firebase API (free, no key).
https://github.com/HackerNews/API
"""

from __future__ import annotations

import httpx

from ..config import cfg
from .translator import translate_to_chinese

_BASE = "https://hacker-news.firebaseio.com/v0"


def fetch_hn_stories() -> list[dict]:
    """Fetch top N Hacker News stories."""
    results: list[dict] = []

    try:
        resp = httpx.get(f"{_BASE}/topstories.json", timeout=10)
        resp.raise_for_status()
        story_ids: list[int] = resp.json()[: cfg.hn_max_stories]

        for sid in story_ids:
            try:
                item_resp = httpx.get(f"{_BASE}/item/{sid}.json", timeout=10)
                item_resp.raise_for_status()
                item = item_resp.json()

                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                        "points": item.get("score", 0),
                        "comment_count": item.get("descendants", 0),
                        "hn_url": f"https://news.ycombinator.com/item?id={sid}",
                    }
                )
            except Exception as e:
                print(f"⚠️  Failed to fetch HN story {sid}: {e}")

    except Exception as e:
        print(f"⚠️  Failed to fetch HN top stories: {e}")

    # Add Chinese translation alongside original English title
    for item in results:
        item["title_cn"] = translate_to_chinese(item["title"])

    return results
