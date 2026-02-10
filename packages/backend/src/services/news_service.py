"""News service — fetches top stories from RSS feeds via feedparser."""

from __future__ import annotations

import re

import feedparser

from ..config import cfg
from .translator import translate_to_chinese

_SOURCE_MAP: dict[str, str] = {
    "BBC News": "BBC News",
    "BBC News - World": "BBC News",
    "NYT > World News": "New York Times",
    "The New York Times": "New York Times",
    "Reuters": "Reuters",
    "Reuters: Top News": "Reuters",
    "CNN.com": "CNN",
    "NPR": "NPR",
    "NPR Topics: News": "NPR",
    "Al Jazeera – Breaking News, World News and Video from Al Jazeera": "Al Jazeera",
    "Al Jazeera English": "Al Jazeera",
    "The Guardian": "The Guardian",
    "Guardian world news": "The Guardian",
    "The Guardian World": "The Guardian",
}


def fetch_news() -> list[dict]:
    """Parse configured RSS feeds and return top N stories, balanced across sources."""
    all_entries: list[dict] = []
    multiplier = cfg.ranking_fetch_multiplier if cfg.ranking_enabled else 1
    effective_max = cfg.news_max_items * multiplier
    # Take at most 3 per feed to ensure source diversity
    per_feed_limit = max(2, effective_max // max(len(cfg.news_feeds), 1) + 1)

    for feed_url in cfg.news_feeds:
        try:
            parsed = feedparser.parse(feed_url)
            source_name = parsed.feed.get("title", feed_url)
            source_name = _SOURCE_MAP.get(source_name, source_name)

            for entry in parsed.entries[:per_feed_limit]:
                all_entries.append(
                    {
                        "headline": entry.get("title", ""),
                        "summary": _clean_summary(
                            entry.get("summary", entry.get("description", ""))
                        ),
                        "source": source_name,
                        "url": entry.get("link", "#"),
                        "category": _extract_category(entry),
                    }
                )
        except Exception as e:
            print(f"⚠️  Failed to parse feed {feed_url}: {e}")

    # De-duplicate by headline, trim to max
    seen: set[str] = set()
    unique: list[dict] = []
    for item in all_entries:
        key = item["headline"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    result = unique[: effective_max]

    # Translate headlines, summaries, and categories to Chinese
    for item in result:
        item["headline"] = translate_to_chinese(item["headline"])
        item["summary"] = translate_to_chinese(item["summary"])
        if item["category"]:
            item["category"] = translate_to_chinese(item["category"])

    return result


def _clean_summary(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&#39;", "'").replace("&quot;", '"')
    if len(text) > 200:
        text = text[:197] + "…"
    return text.strip()


def _extract_category(entry: dict) -> str:
    tags = entry.get("tags", [])
    if tags and isinstance(tags, list):
        return tags[0].get("term", "")
    return ""
