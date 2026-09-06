"""Exercise production _collect with the pinned SDK's real event data models."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from test_editor import FakeTurn, live_editor
from test_editor import bundle as bundle
from test_editor import fake_sdk as fake_sdk
from test_editor import packet as packet
from test_usage import notification

from newsletter.editor import EditorError, _collect
from newsletter.usage import codex_usage, summarize_usage, usage_scope


class EventTurn:
    def __init__(self, events):
        self.events = events

    async def stream(self):
        for event in self.events:
            if isinstance(event, BaseException):
                raise event
            yield event


def usage_event():
    from openai_codex.generated.v2_all import ThreadTokenUsageUpdatedNotification
    from openai_codex.models import Notification

    payload = ThreadTokenUsageUpdatedNotification.model_validate(notification())
    return Notification(method="thread/tokenUsage/updated", payload=payload)


def final_event():
    return SimpleNamespace(
        method="item/completed",
        payload={
            "item": {
                "type": "agentMessage",
                "phase": "final_answer",
                "text": json.dumps({"synthetic": True}),
            }
        },
    )


def end_event(status="completed"):
    return SimpleNamespace(method="turn/completed", payload={"turn": {"status": status}})


async def test_collect_captures_real_sdk_usage_without_changing_return_tuple():
    records = []
    with usage_scope(records.append, "editor"), codex_usage("fixture") as usage:
        usage.start_turn()
        result = await _collect(EventTurn([usage_event(), final_event(), end_event()]))
    assert result == ('{"synthetic": true}', set(), False)
    assert summarize_usage(records)["usage"]["total_tokens"] == 120
    assert not summarize_usage(records)["partial"]


@pytest.mark.parametrize(
    "ending", [end_event("failed"), RuntimeError("fixture"), asyncio.CancelledError()]
)
async def test_collect_keeps_reported_usage_even_when_stream_fails(ending):
    records = []
    error = type(ending) if isinstance(ending, BaseException) else EditorError
    with pytest.raises(error):
        with usage_scope(records.append, "research:fixture"), codex_usage("fixture") as usage:
            usage.start_turn()
            await _collect(EventTurn([usage_event(), ending]))
    assert summarize_usage(records)["usage"]["total_tokens"] == 120
    assert summarize_usage(records)["partial"]


async def test_no_usage_event_is_unknown_not_an_empty_successful_measurement():
    records = []
    with usage_scope(records.append, "editor"), codex_usage("fixture") as usage:
        usage.start_turn()
        await _collect(EventTurn([final_event(), end_event()]))
    assert summarize_usage(records)["usage"] is None


async def test_execute_captures_original_and_provenance_correction_as_one_thread(
    tmp_path, fake_sdk, packet
):
    research = {"state": "collected", "note": "synthetic", "packets": [packet["content"]]}

    class MeteredTurn(FakeTurn):
        def __init__(self, tokens, research_enabled):
            super().__init__(research, research=research_enabled)
            self.tokens = tokens

        async def stream(self):
            yield SimpleNamespace(
                method="thread/tokenUsage/updated", payload=notification(self.tokens)
            )
            async for event in super().stream():
                yield event

    fake_sdk.turns = [MeteredTurn(100, False), MeteredTurn(300, True)]
    records = []
    with usage_scope(records.append, "research:synthetic"):
        await live_editor(tmp_path).execute("{}", {}, "synthetic", tmp_path / "workspace")
    assert len(fake_sdk.prompts) == 2
    assert summarize_usage(records)["invocations"] == 1
    assert summarize_usage(records)["usage"]["total_tokens"] == 320
    assert records[-1]["turns_started"] == 2


async def test_invalid_model_result_still_has_reported_usage(tmp_path, fake_sdk):
    class InvalidTurn(FakeTurn):
        async def stream(self):
            yield usage_event()
            async for event in super().stream():
                yield event

    fake_sdk.turn = InvalidTurn("not JSON", research=False)
    records = []
    with pytest.raises(EditorError):
        with usage_scope(records.append, "editor"):
            await live_editor(tmp_path).execute("{}", {}, "synthetic", tmp_path / "workspace")
    assert summarize_usage(records)["usage"]["total_tokens"] == 120
    assert records[-1]["status"] == "failed"
