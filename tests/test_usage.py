"""Offline provider-event accounting; no SDK process, credentials or model calls."""

import asyncio
import copy

import pytest

from newsletter.usage import (
    codex_usage,
    normalize_usage_summary,
    observe_codex_usage,
    summarize_usage,
    usage_footer,
    usage_scope,
)


def notification(
    input_tokens=100, output_tokens=20, cached=60, reasoning=10, **extra
):
    counts = {
        "inputTokens": input_tokens,
        "cachedInputTokens": cached,
        "outputTokens": output_tokens,
        "reasoningOutputTokens": reasoning,
        "totalTokens": input_tokens + output_tokens,
        **extra,
    }
    return {
        "threadId": "thread-test",
        "turnId": "turn-test",
        "tokenUsage": {
            "total": counts,
            "last": counts,
            "modelContextWindow": 200000,
        },
    }


def observe(payload=None):
    observe_codex_usage("thread/tokenUsage/updated", payload or notification())


def complete():
    observe_codex_usage(
        "turn/completed", {"turn": {"id": "turn-test", "status": "completed"}}
    )


def record_one(payload=None):
    records = []
    with (
        usage_scope(records.append, "research:synthetic"),
        codex_usage("fixture-model") as usage,
    ):
        usage.start_turn()
        usage.bind_turn("thread-test", "turn-test")
        observe(payload)
        complete()
    return records


def test_cumulative_snapshots_replace_and_correction_does_not_double_count():
    records = []
    with (
        usage_scope(records.append, "research:synthetic"),
        codex_usage("fixture-model") as usage,
    ):
        usage.start_turn()
        observe(notification(100, 20))
        observe(notification(150, 35))
        observe(
            notification(150, 35)
        )  # Duplicate snapshot is not another request.
        complete()
        usage.start_turn()
        observe(notification(250, 70, 120, 30))
        complete()
    summary = summarize_usage(records)
    assert summary == {
        "usage": {
            "input_tokens": 250,
            "cached_input_tokens": 120,
            "output_tokens": 70,
            "reasoning_output_tokens": 30,
            "total_tokens": 320,
        },
        "invocations": 1,
        "missing_invocations": 0,
        "partial": False,
    }
    assert records[0]["usage"] is None  # Durable placeholder before turn/start.
    assert records[-1]["turns_started"] == records[-1]["turns_completed"] == 2
    assert records[-1]["turns_with_usage"] == 2
    assert records[-1]["stage"] == "research:synthetic"
    assert "320 tokens" in usage_footer(summary)


def test_separate_threads_sum_only_their_latest_totals():
    records = record_one() + record_one(notification(300, 50))
    summary = summarize_usage(records)
    assert summary["invocations"] == 2
    assert summary["usage"]["total_tokens"] == 470
    assert summary["usage"]["input_tokens"] == 400


def test_unknown_is_not_zero_and_real_reported_zero_is_preserved():
    assert summarize_usage([])["usage"] is None
    records = []
    with usage_scope(records.append, "editor"), codex_usage("fixture") as usage:
        usage.start_turn()
        complete()
    summary = summarize_usage(records)
    assert summary["usage"] is None and summary["missing_invocations"] == 1
    assert "0 tokens" not in usage_footer(summary)
    summary = summarize_usage(record_one(notification(0, 0, 0, 0)))
    assert summary["usage"]["total_tokens"] == 0 and not summary["partial"]


def test_missing_correction_usage_retains_partial_known_amount():
    records = []
    with usage_scope(records.append, "editor"), codex_usage("fixture") as usage:
        usage.start_turn()
        observe()
        complete()
        usage.start_turn()
        complete()
    summary = summarize_usage(records)
    assert summary["usage"]["total_tokens"] == 120 and summary["partial"]
    assert "未含未返回用量的调用" in usage_footer(summary)


@pytest.mark.parametrize(
    "failure", [RuntimeError("synthetic"), asyncio.CancelledError()]
)
def test_failure_and_cancellation_flush_known_usage_without_claiming_complete(
    failure,
):
    records = []
    with pytest.raises(type(failure)):
        with (
            usage_scope(records.append, "editor"),
            codex_usage("fixture") as usage,
        ):
            usage.start_turn()
            observe()
            raise failure
    assert records[-1]["status"] == "failed"
    assert records[-1]["usage"]["total_tokens"] == 120
    assert records[-1]["partial"]


@pytest.mark.parametrize("bad", [None, True, -1, 1.5, "100", 2**63])
def test_malformed_counters_do_not_become_zero_or_leak_other_payload(bad):
    value = notification()
    value["tokenUsage"]["total"]["inputTokens"] = bad
    value["secret_fixture"] = "do-not-persist-payload"
    records = record_one(value)
    assert records[-1]["usage"] is None and records[-1]["partial"]
    assert "do-not-persist-payload" not in repr(records)


@pytest.mark.parametrize(
    "key,value",
    [
        ("totalTokens", 135),
        ("cachedInputTokens", 200),
        ("reasoningOutputTokens", 30),
    ],
)
def test_provider_total_is_preserved_not_recomputed_when_subsets_disagree(
    key, value
):
    records = record_one(notification(**{key: value}))
    summary = summarize_usage(records)
    assert summary["partial"]
    assert summary["usage"]["total_tokens"] == (
        135 if key == "totalTokens" else 120
    )


def test_counter_reset_keeps_last_trusted_snapshot_and_marks_partial():
    records = []
    with usage_scope(records.append, "editor"), codex_usage("fixture") as usage:
        usage.start_turn()
        observe(notification(1000, 100))
        observe(notification(100, 20))
        complete()
    assert records[-1]["usage"]["total_tokens"] == 1100
    assert records[-1]["partial"]


@pytest.mark.parametrize("field", ["threadId", "turnId"])
def test_unrelated_usage_event_is_not_attributed_to_active_turn(field):
    payload = notification()
    payload[field] = "unrelated"
    records = record_one(payload)
    assert records[-1]["usage"] is None


def test_sink_failure_is_sanitized_and_not_swallowed():
    def broken(record):
        raise RuntimeError("synthetic-secret")

    with pytest.raises(RuntimeError, match="^usage_recording_failed$") as exc:
        with usage_scope(broken, "editor"), codex_usage("fixture") as usage:
            usage.start_turn()
    assert exc.value.__suppress_context__


def test_no_model_attempt_does_not_create_a_zero_usage_entry():
    records = []
    with usage_scope(records.append, "editor"), codex_usage("fixture"):
        pass  # SDK startup only, no turn/start.
    assert records == []


async def test_contextvar_scopes_do_not_cross_concurrent_research_tasks():
    async def run(stage, input_tokens):
        records = []
        with (
            usage_scope(records.append, stage),
            codex_usage("fixture") as usage,
        ):
            usage.start_turn()
            await asyncio.sleep(0)
            observe(notification(input_tokens, 20))
            complete()
        return records

    first, second = await asyncio.gather(run("science", 100), run("world", 200))
    assert {r["stage"] for r in first} == {"science"}
    assert {r["stage"] for r in second} == {"world"}
    assert first[-1]["usage"]["total_tokens"] == 120
    assert second[-1]["usage"]["total_tokens"] == 220


def test_sink_cannot_mutate_in_memory_counters():
    records = []

    def sink(record):
        records.append(copy.deepcopy(record))
        record["usage"] = None

    with usage_scope(sink, "editor"), codex_usage("fixture") as usage:
        usage.start_turn()
        observe()
        complete()
    assert records[-1]["usage"]["total_tokens"] == 120


def test_proto_json_uint64_strings_and_defaults_normalize_losslessly():
    summary = summarize_usage(record_one())
    wire = {
        **summary,
        "usage": {key: str(value) for key, value in summary["usage"].items()},
    }
    assert normalize_usage_summary(wire) == summary
    assert normalize_usage_summary({})["usage"] is None
    assert normalize_usage_summary({"usage": {}})["usage"]["total_tokens"] == 0


@pytest.mark.parametrize(
    "bad", [True, -1, "-1", "1.2", "１", "secret", "9" * 21]
)
def test_footer_rejects_invalid_proto_json_counter(bad):
    with pytest.raises(ValueError, match="^invalid_usage_summary$"):
        normalize_usage_summary({"usage": {"total_tokens": bad}})


def test_mock_does_not_present_synthetic_usage_as_real():
    text = usage_footer(summarize_usage(record_one()), is_fixture=True)
    assert "MOCK" in text and "120" not in text


def test_unknown_gemini_usage_explicitly_excluded_not_assumed_zero():
    assert "Todofy/Gemini 用量未计入" in usage_footer(
        summarize_usage(record_one())
    )
