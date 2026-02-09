"""GitHub Trending service — scrapes daily trending repos by language."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from ..config import cfg
from .translator import translate_to_chinese

_BASE = "https://github.com/trending"


def fetch_github_trending() -> list[dict]:
    """Fetch daily trending repos for configured languages."""
    results: list[dict] = []

    for lang in cfg.github_trending_languages:
        try:
            url = f"{_BASE}/{lang.lower()}" if lang else _BASE
            display_lang = lang or "overall"
            resp = httpx.get(
                url,
                params={"since": "daily"},
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 newsletter-bot/1.0"},
            )
            resp.raise_for_status()
            repos = _parse_trending_page(resp.text, display_lang)
            results.extend(repos[: cfg.github_trending_max_per_lang])
        except Exception as e:
            print(f"⚠️  Failed to fetch GitHub trending for {display_lang}: {e}")

    return results


def _parse_trending_page(html: str, language: str) -> list[dict]:
    """Parse GitHub trending page HTML into structured repo data."""
    soup = BeautifulSoup(html, "html.parser")
    repos: list[dict] = []

    for article in soup.select("article.Box-row"):
        try:
            # ── Repo name & URL ──
            h2 = article.select_one("h2")
            if not h2:
                continue
            a_tag = h2.select_one("a")
            if not a_tag:
                continue
            name = a_tag.get_text(strip=True).replace("\n", "").replace(" ", "")
            href = a_tag.get("href", "")
            url = "https://github.com" + (href if isinstance(href, str) else href[0])

            # ── Description ──
            desc_tag = article.select_one("p")
            desc = desc_tag.get_text(strip=True) if desc_tag else ""

            # ── Total stars ──
            star_links = article.select("a.Link--muted.d-inline-block.mr-3")
            total_stars = 0
            if star_links:
                star_text = star_links[0].get_text(strip=True).replace(",", "")
                total_stars = int("".join(c for c in star_text if c.isdigit()) or "0")

            # ── Stars today ──
            today_span = article.select_one("span.d-inline-block.float-sm-right")
            today_stars = 0
            if today_span:
                today_text = today_span.get_text(strip=True)
                today_stars = int(
                    "".join(c for c in today_text.split("star")[0] if c.isdigit()) or "0"
                )

            repos.append(
                {
                    "name": name,
                    "description": desc,
                    "description_cn": translate_to_chinese(desc) if desc else "",
                    "language": language.capitalize(),
                    "stars": total_stars,
                    "today_stars": today_stars,
                    "url": url,
                }
            )
        except Exception:
            continue

    return repos
