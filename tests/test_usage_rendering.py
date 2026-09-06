"""Small, static footer with a frozen render hash; no remote assets or model data."""

import copy

from test_rendering import SAMPLE_DRAFT, SAMPLE_PACKETS
from test_usage import notification, record_one

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
    assert "非缓存输入 40 · 缓存输入 60 · 输出 20" in with_usage["html"]
    assert "非缓存输入 40 · 缓存输入 60 · 输出 20" in with_usage["text"]
    assert "不重复相加" not in with_usage["text"]
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


def test_large_cached_usage_is_split_into_disjoint_parts_without_claiming_plan_percent():
    summary = summarize_usage(record_one(notification(6_000_000, 90_000, cached=5_000_000)))
    result = render(summary)
    for output in (result["html"], result["text"]):
        assert "6,090,000 tokens" in output
        assert "非缓存输入 1,000,000 · 缓存输入 5,000,000 · 输出 90,000" in output
        assert "11,090,000" not in output
        assert "plan" not in output.lower()


def test_inconsistent_counts_never_create_negative_uncached_input_or_silent_zero():
    summary = summarize_usage(record_one(notification(100, 20, cached=101)))
    result = render(summary)
    assert "输入/输出拆分不可确定" in result["text"]
    assert "非缓存输入 -1" not in result["text"]
    assert "非缓存输入 0" not in result["text"]
    assert "部分用量" in result["text"]
