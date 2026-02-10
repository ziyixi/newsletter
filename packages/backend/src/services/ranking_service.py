"""
Ranking service — uses Gemini to rank fetched items by relevance.

After all services over-fetch items (controlled by ``ranking.fetchMultiplier``),
this module sends the collected items to Gemini and asks it to return ranked
indices.  The final lists are trimmed back to the configured limits.

Two LLM calls are made:
  1. **Current-events** — ranks news + Hacker News stories together.
  2. **Tech-content**  — ranks arXiv papers + GitHub trending repos together.

If Gemini is unavailable or the call fails, the original ordering is kept
(graceful fallback).
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import cfg
from . import gemini_client


# ── public API ────────────────────────────────────────────────


def rank_sections(sections: dict[str, Any]) -> dict[str, Any]:
    """Rank and trim over-fetched sections using LLM.

    *sections* is the dict returned by ``_fetch_all()``.  This function
    mutates it in-place **and** returns it for convenience.
    """
    if not cfg.ranking_enabled:
        return sections

    client = gemini_client.get_client()
    if client is None:
        print("⚠️  Ranking skipped — no Gemini API key")
        return _trim_to_limits(sections)

    print("🏆  Ranking items with LLM …")

    # ── Call 1: current-events (news + HN) ──
    news: list[dict] = sections.get("news", [])
    hn: list[dict] = sections.get("hn", [])
    news, hn = _rank_current_events(client, news, hn)
    sections["news"] = news
    sections["hn"] = hn

    # ── Call 2: tech-content (arXiv + GitHub trending) ──
    arxiv_papers: list[dict] = sections.get("arxiv", [])
    github: list[dict] = sections.get("github_trending", [])
    arxiv_papers, github = _rank_tech_content(client, arxiv_papers, github)
    sections["arxiv"] = arxiv_papers
    sections["github_trending"] = github

    print("  ✅  Ranking complete")
    return sections


# ── internal helpers ──────────────────────────────────────────


def _trim_to_limits(sections: dict[str, Any]) -> dict[str, Any]:
    """Fallback: just cut each list to configured limits (no LLM)."""
    news = sections.get("news", [])
    sections["news"] = news[: cfg.news_max_items]

    hn = sections.get("hn", [])
    sections["hn"] = hn[: cfg.hn_max_stories]

    arxiv_papers = sections.get("arxiv", [])
    total_arxiv_limit = sum(q.get("maxResults", 3) for q in cfg.arxiv_queries)
    sections["arxiv"] = arxiv_papers[:total_arxiv_limit]

    gh = sections.get("github_trending", [])
    total_gh_limit = cfg.github_trending_max_per_lang * len(cfg.github_trending_languages)
    sections["github_trending"] = gh[:total_gh_limit]

    return sections


def _rank_current_events(
    client: Any,
    news: list[dict],
    hn: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Rank news and HN stories together via one LLM call."""
    news_limit = cfg.news_max_items
    hn_limit = cfg.hn_max_stories

    # Build summaries for LLM
    items_text = ""
    items_text += "=== NEWS ===\n"
    for i, n in enumerate(news):
        headline = n.get("headline", n.get("title", ""))
        source = n.get("source", "")
        items_text += f"N{i}: [{source}] {headline}\n"

    items_text += "\n=== HACKER NEWS ===\n"
    for i, h in enumerate(hn):
        title = h.get("title", "")
        points = h.get("points", 0)
        items_text += f"H{i}: [points={points}] {title}\n"

    prompt = (
        "你是一位新闻编辑。请根据以下标准对新闻和Hacker News条目进行排名：\n"
        "1. 重要性和影响力\n"
        "2. 信息价值和知识含量\n"
        "3. 话题多样性（避免重复话题）\n\n"
        f"{items_text}\n"
        f"请从NEWS中选出最重要的 {news_limit} 条，从HACKER NEWS中选出最重要的 {hn_limit} 条。\n"
        "请严格按以下JSON格式回复，不要多余内容：\n"
        '{"news": [0, 2, 1], "hn": [3, 1, 0]}\n'
        "其中数组内是原始编号（如N0, N2, …和H3, H1, …），按推荐顺序排列。"
    )

    text = gemini_client.generate(client, prompt)
    if text is None:
        return news[:news_limit], hn[:hn_limit]

    indices = _parse_index_json(text)
    ranked_news = _reorder(news, indices.get("news"), news_limit)
    ranked_hn = _reorder(hn, indices.get("hn"), hn_limit)
    return ranked_news, ranked_hn


def _rank_tech_content(
    client: Any,
    arxiv_papers: list[dict],
    github: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Rank arXiv papers and GitHub trending repos together via one LLM call."""
    total_arxiv_limit = sum(q.get("maxResults", 3) for q in cfg.arxiv_queries)
    total_gh_limit = cfg.github_trending_max_per_lang * len(cfg.github_trending_languages)

    items_text = ""
    items_text += "=== ARXIV PAPERS ===\n"
    for i, p in enumerate(arxiv_papers):
        title = p.get("title", "")
        cat = p.get("category", "")
        items_text += f"A{i}: [{cat}] {title}\n"

    items_text += "\n=== GITHUB TRENDING ===\n"
    for i, g in enumerate(github):
        name = g.get("name", "")
        desc = g.get("description", "")
        stars = g.get("stars", 0)
        lang = g.get("language", "")
        items_text += f"G{i}: [{lang}, ★{stars}] {name} — {desc}\n"

    prompt = (
        "你是一位技术编辑。请根据以下标准对arXiv论文和GitHub项目进行排名：\n"
        "1. 技术创新性和影响力\n"
        "2. 实用价值和学习价值\n"
        "3. 话题多样性\n\n"
        f"{items_text}\n"
        f"请从ARXIV PAPERS中选出最重要的 {total_arxiv_limit} 篇，"
        f"从GITHUB TRENDING中选出最重要的 {total_gh_limit} 个项目。\n"
        "请严格按以下JSON格式回复，不要多余内容：\n"
        '{"arxiv": [0, 2, 1], "github": [3, 1, 0]}\n'
        "其中数组内是原始编号（如A0, A2, …和G3, G1, …），按推荐顺序排列。"
    )

    text = gemini_client.generate(client, prompt)
    if text is None:
        return arxiv_papers[:total_arxiv_limit], github[:total_gh_limit]

    indices = _parse_index_json(text)
    ranked_arxiv = _reorder(arxiv_papers, indices.get("arxiv"), total_arxiv_limit)
    ranked_gh = _reorder(github, indices.get("github"), total_gh_limit)
    return ranked_arxiv, ranked_gh


def _parse_index_json(text: str) -> dict[str, list[int]]:
    """Extract the JSON object from possibly decorated LLM output."""
    # Strip markdown code fences if present
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.strip().rstrip("`")

    # Find the outermost JSON object using brace matching
    start = text.find("{")
    if start == -1:
        return {}
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                json_str = text[start : i + 1]
                break
    else:
        return {}

    try:
        data = json.loads(json_str)
        return {
            k: [int(x) for x in v] for k, v in data.items() if isinstance(v, list)
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _reorder(items: list[dict], indices: list[int] | None, limit: int) -> list[dict]:
    """Reorder *items* by *indices*, then trim to *limit*.

    Invalid indices are silently skipped; any remaining slots are filled
    with items not yet selected, preserving their original order.
    """
    if not indices:
        return items[:limit]

    selected: list[dict] = []
    used: set[int] = set()

    for idx in indices:
        if 0 <= idx < len(items) and idx not in used:
            selected.append(items[idx])
            used.add(idx)
        if len(selected) >= limit:
            break

    # Fill remaining slots with unselected items
    if len(selected) < limit:
        for idx, item in enumerate(items):
            if idx not in used:
                selected.append(item)
                if len(selected) >= limit:
                    break

    return selected
