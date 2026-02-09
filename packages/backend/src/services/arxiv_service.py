"""
arXiv service — fetches latest papers and summarizes with Gemini.

Uses the ``arxiv`` package (lukasschwab/arxiv.py) for reliable API access.

Categories:
  - cs.CL (Computation and Language) → LLM papers
  - cs.DC (Distributed Computing) → HPC papers

Falls back to Google Translate if GEMINI_API_KEY is not set.
"""

from __future__ import annotations

import os
from typing import Any

import arxiv

from ..config import cfg


def fetch_arxiv_papers() -> list[dict]:
    """Fetch latest arXiv papers for configured categories and summarize."""
    results: list[dict] = []
    client = arxiv.Client(page_size=10, delay_seconds=3.0, num_retries=3)

    for qcfg in cfg.arxiv_queries:
        try:
            max_results = qcfg.get("maxResults", 3)
            search = arxiv.Search(
                query=qcfg["query"],
                max_results=max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )

            for paper in client.results(search):
                # Authors (first 3)
                authors: list[str] = [a.name for a in paper.authors[:3]]
                author_str = ", ".join(authors)
                if len(paper.authors) > 3:
                    author_str += " et al."

                results.append(
                    {
                        "title": paper.title,
                        "title_cn": "",
                        "summary": "",
                        "_abstract": paper.summary.replace("\n", " ").strip(),
                        "authors": author_str,
                        "url": paper.entry_id,
                        "category": qcfg.get("label", ""),
                    }
                )
        except Exception as e:
            print(f"⚠️  Failed to fetch arXiv ({qcfg.get('label', '?')}): {e}")

    # Summarize with Gemini (or fallback)
    return _summarize(results)


# ── AI Summarization ─────────────────────────────────────────


def _summarize(papers: list[dict]) -> list[dict]:
    """Summarize papers using Gemini, with graceful fallback."""
    api_key = os.getenv("GEMINI_API_KEY", "")

    if api_key:
        papers = _summarize_with_gemini(papers, api_key)
    else:
        print("⚠️  GEMINI_API_KEY not set — using fallback translation")
        papers = _summarize_fallback(papers)

    # Remove internal _abstract field
    for p in papers:
        p.pop("_abstract", None)

    return papers


_GEMINI_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]


def _summarize_with_gemini(papers: list[dict], api_key: str) -> list[dict]:
    """Use Gemini to translate titles and generate one-line Chinese summaries."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        models_to_try = [cfg.gemini_model, *_GEMINI_FALLBACK_MODELS]

        for p in papers:
            _gemini_summarize_paper(client, models_to_try, p)
    except ImportError:
        print("⚠️  google-genai not installed — using fallback")
        papers = _summarize_fallback(papers)

    return papers


def _gemini_summarize_paper(
    client: Any, models: list[str], paper: dict
) -> None:
    """Try each model in *models* until one succeeds."""
    prompt = (
        "请为以下学术论文提供：\n"
        "1. 中文标题翻译\n"
        "2. 一句话中文摘要（不超过80字）\n\n"
        f"标题：{paper['title']}\n"
        f"摘要：{paper.get('_abstract', '')[:500]}\n\n"
        "请严格按以下格式回复，不要多余内容：\n"
        "标题：<中文标题>\n"
        "摘要：<一句话中文摘要>"
    )

    for model_name in models:
        try:
            resp = client.models.generate_content(  # type: ignore[union-attr]
                model=model_name,
                contents=prompt,
            )
            if resp.text:
                _parse_gemini_response(paper, resp.text.strip())
                if paper.get("title_cn"):
                    return  # success
        except Exception as e:
            print(f"⚠️  Gemini ({model_name}) failed for paper: {e}")

    # All models exhausted — use translation fallback
    _fallback_single(paper)


def _parse_gemini_response(paper: dict, text: str) -> None:
    """Parse Gemini's structured response into paper dict."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(("标题：", "标题:")):
            paper["title_cn"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif line.startswith(("摘要：", "摘要:")):
            paper["summary"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()

    # Ensure we have values
    if not paper["title_cn"]:
        _fallback_single(paper)


def _summarize_fallback(papers: list[dict]) -> list[dict]:
    """Fallback: use Google Translate for titles and truncated abstract."""
    for p in papers:
        _fallback_single(p)
    return papers


def _fallback_single(paper: dict) -> None:
    """Fallback for a single paper."""
    from .translator import translate_to_chinese

    if not paper.get("title_cn"):
        paper["title_cn"] = translate_to_chinese(paper["title"])
    if not paper.get("summary"):
        abstract = paper.get("_abstract", "")
        paper["summary"] = (abstract[:150] + "…") if len(abstract) > 150 else abstract
