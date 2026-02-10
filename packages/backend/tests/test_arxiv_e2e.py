"""
E2E test for the arXiv fetching service.

Validates that arXiv papers can be fetched reliably without hitting
HTTP 429 rate limits, even when multiple queries are configured.

Usage:
  uv run python tests/test_arxiv_e2e.py          # standalone
"""

from __future__ import annotations

import socket
import sys
import time

import arxiv


def _arxiv_reachable() -> bool:
    """Return True if export.arxiv.org is reachable."""
    try:
        socket.create_connection(("export.arxiv.org", 443), timeout=5).close()
        return True
    except OSError:
        return False


# ── Helpers ──────────────────────────────────────────────────


def _fetch_papers(query: str, max_results: int, client: arxiv.Client) -> list[dict]:
    """Fetch papers for a single query, returning a list of dicts."""
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    papers: list[dict] = []
    for paper in client.results(search):
        authors = [a.name for a in paper.authors[:3]]
        author_str = ", ".join(authors)
        if len(paper.authors) > 3:
            author_str += " et al."
        papers.append(
            {
                "title": paper.title,
                "authors": author_str,
                "url": paper.entry_id,
                "abstract_len": len(paper.summary),
            }
        )
    return papers


# ── Tests ────────────────────────────────────────────────────


def test_arxiv_single_query() -> None:
    """Fetch a small number of LLM papers from arXiv."""
    client = arxiv.Client(page_size=10, delay_seconds=5.0, num_retries=5)
    papers = _fetch_papers("cat:cs.CL AND abs:LLM", max_results=3, client=client)
    assert len(papers) > 0, "Expected at least 1 paper from cs.CL+LLM query"
    for p in papers:
        assert p["title"], "Paper title must not be empty"
        assert p["url"].startswith("http"), "Paper URL must be a valid link"
        assert p["abstract_len"] > 0, "Paper must have an abstract"
    print(f"  ✅ Single query: fetched {len(papers)} papers")


def test_arxiv_multiple_queries_no_429() -> None:
    """Fetch from two categories back-to-back without 429 errors."""
    client = arxiv.Client(page_size=10, delay_seconds=5.0, num_retries=5)
    queries = [
        {"query": "cat:cs.CL AND abs:LLM", "label": "LLM", "max": 3},
        {"query": "cat:cs.DC AND abs:HPC", "label": "HPC", "max": 2},
    ]

    all_papers: list[dict] = []
    for i, q in enumerate(queries):
        if i > 0:
            time.sleep(5)  # pause between queries to avoid 429
        papers = _fetch_papers(q["query"], q["max"], client)
        assert len(papers) > 0, f"Expected papers from {q['label']} query"
        all_papers.extend(papers)
        print(f"  ✅ {q['label']}: fetched {len(papers)} papers")

    assert len(all_papers) >= 2, "Expected at least 2 papers total"
    print(f"  ✅ Total: {len(all_papers)} papers fetched across {len(queries)} queries")


def test_arxiv_paper_fields() -> None:
    """Validate that paper fields are well-formed."""
    client = arxiv.Client(page_size=10, delay_seconds=5.0, num_retries=5)
    search = arxiv.Search(
        query="cat:cs.CL AND abs:LLM",
        max_results=1,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    results = list(client.results(search))
    assert len(results) == 1, "Expected exactly 1 result"
    paper = results[0]
    assert paper.title and len(paper.title) > 5, "Title too short"
    assert paper.summary and len(paper.summary) > 20, "Abstract too short"
    assert paper.entry_id.startswith("http"), "entry_id must be a URL"
    assert len(paper.authors) > 0, "Paper must have at least one author"
    print(f"  ✅ Paper fields OK: '{paper.title[:60]}…'")


# ── Standalone runner ────────────────────────────────────────


def main() -> None:
    print("=" * 50)
    print("🧪  arXiv E2E Test")
    print("=" * 50)

    if not _arxiv_reachable():
        print("\n⚠️  Skipping: arXiv API not reachable (no network)")
        sys.exit(0)

    tests = [test_arxiv_single_query, test_arxiv_multiple_queries_no_429, test_arxiv_paper_fields]
    failed = 0

    for test_fn in tests:
        name = test_fn.__name__
        print(f"\n▶ {name}")
        try:
            test_fn()
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1

    print()
    if failed:
        print(f"❌  {failed}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"✅  All {len(tests)} tests passed")


if __name__ == "__main__":
    main()
