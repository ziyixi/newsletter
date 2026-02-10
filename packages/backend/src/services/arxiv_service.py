"""
arXiv service — fetches latest papers and summarizes with Gemini.

Uses the ``arxiv`` package (lukasschwab/arxiv.py) for reliable API access.

Categories:
  - cs.CL (Computation and Language) → LLM papers
  - cs.DC (Distributed Computing) → HPC papers

Falls back to Google Translate if GEMINI_API_KEY is not set.
"""

from __future__ import annotations

import arxiv

from ..config import cfg
from . import gemini_client


def fetch_arxiv_papers() -> list[dict]:
    """Fetch latest arXiv papers for configured categories and summarize."""
    results: list[dict] = []
    client = arxiv.Client(page_size=10, delay_seconds=3.0, num_retries=3)
    multiplier = cfg.ranking_fetch_multiplier if cfg.ranking_enabled else 1

    for qcfg in cfg.arxiv_queries:
        try:
            max_results = qcfg.get("maxResults", 3) * multiplier
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
    """Summarize papers using Gemini (batch), with graceful fallback."""
    client = gemini_client.get_client()

    if client is not None:
        papers = _summarize_batch_gemini(papers, client)
    else:
        print("⚠️  GEMINI_API_KEY not set — using fallback translation")
        papers = _summarize_fallback(papers)

    # Remove internal _abstract field
    for p in papers:
        p.pop("_abstract", None)

    return papers


def _summarize_batch_gemini(papers: list[dict], client: object) -> list[dict]:
    """Batch-summarise all papers in a single Gemini call (saves API quota)."""
    if not papers:
        return papers

    # Build a numbered list for the prompt
    paper_lines: list[str] = []
    for i, p in enumerate(papers):
        paper_lines.append(
            f"[{i}] 标题：{p['title']}\n    摘要：{p.get('_abstract', '')[:400]}"
        )
    numbered_text = "\n".join(paper_lines)

    prompt = (
        "请为以下每篇学术论文提供：\n"
        "1. 中文标题翻译\n"
        "2. 一句话中文摘要（不超过80字）\n\n"
        f"{numbered_text}\n\n"
        "请严格按以下格式逐篇回复，不要多余内容：\n"
        "[编号]\n"
        "标题：<中文标题>\n"
        "摘要：<一句话中文摘要>\n"
    )

    text = gemini_client.generate(client, prompt)
    if text is None:
        return _summarize_fallback(papers)

    _parse_batch_response(papers, text)

    # Fill in any that the batch missed
    for p in papers:
        if not p.get("title_cn"):
            _fallback_single(p)

    return papers


def _parse_batch_response(papers: list[dict], text: str) -> None:
    """Parse the batch Gemini response and populate paper dicts."""
    current_idx: int | None = None

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Detect "[0]", "[1]", etc.
        if line.startswith("[") and "]" in line:
            try:
                idx_str = line[1 : line.index("]")]
                current_idx = int(idx_str)
            except (ValueError, IndexError):
                pass
            continue

        if current_idx is not None and 0 <= current_idx < len(papers):
            p = papers[current_idx]
            if line.startswith(("标题：", "标题:")):
                p["title_cn"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith(("摘要：", "摘要:")):
                p["summary"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()


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
