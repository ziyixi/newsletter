"""Small, static footer with a frozen render hash; no remote assets or model data."""

import copy

from test_rendering import SAMPLE_DRAFT, SAMPLE_PACKETS
from test_usage import record_one

from newsletter.rendering import render_edition
from newsletter.usage import summarize_usage


def render(usage=None, *, fixture=False):
    packets = copy.deepcopy(SAMPLE_PACKETS)
    packets[0]["is_fixture"] = fixture
    return render_edition(SAMPLE_DRAFT, packets, "2026-09-05", usage=usage)


def test_footer_below_branding_also_ends_plain_text_and_changes_frozen_hash():
    summary = summarize_usage(record_one())
    without = render()
    with_usage = render(summary)
    assert "Codex 已记录 120 tokens" in with_usage["html"]
    assert with_usage["html"].index("Codex 已记录") > with_usage["html"].index("THE DAILY BRIEF")
    assert "text-align:right" in with_usage["html"]
    assert with_usage["text"].rstrip().endswith("Todofy/Gemini 用量未计入。")
    assert without["render_hash"] != with_usage["render_hash"]
    assert render(summary) == with_usage


def test_uint64_wire_shape_does_not_change_html_or_text():
    summary = summarize_usage(record_one())
    wire = {**summary, "usage": {key: str(value) for key, value in summary["usage"].items()}}
    assert render(wire) == render(summary)


def test_existing_call_without_usage_keeps_footer_absent():
    assert "tokens" not in render()["html"]


def test_partial_footer_does_not_claim_complete_consumption():
    summary = summarize_usage(record_one())
    summary["partial"] = True
    assert "部分用量，未含未返回用量的调用" in render(summary)["html"]


def test_mock_footer_cannot_look_like_real_billable_usage():
    result = render(summarize_usage(record_one()), fixture=True)
    assert "MOCK · 用量统计仅为流程演示" in result["html"]
    assert "120 tokens" not in result["html"]
