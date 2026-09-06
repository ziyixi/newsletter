"""One bounded provenance correction, with synthetic SDK events and no network."""

import copy
import json

import pytest
from test_editor import FakeTurn, discovery_turn, live_editor
from test_editor import bundle as bundle
from test_editor import fake_sdk as fake_sdk
from test_editor import packet as packet

from newsletter import editor
from newsletter.store import Store
from newsletter.workflow.definition import parse_definition
from newsletter.workflow.engine import NodeContext
from newsletter.workflow.nodes import EditorialNodes


def approval(bundle, shape, *, passed=True):
    value = copy.deepcopy(bundle)
    value["review"] = {"passed": passed, "findings": ["Synthetic review only."]}
    return value if shape == "editor" else value["review"]


def limited_turn(value, missing):
    if missing == "both":
        return FakeTurn(value, research=False)
    return discovery_turn(value, omit_action=missing)


@pytest.mark.parametrize("shape", ["editor", "review"])
@pytest.mark.parametrize("missing", ["search", "openPage", "both"])
async def test_claimed_pass_gets_same_thread_action_correction(
    tmp_path, fake_sdk, bundle, shape, missing
):
    value = approval(bundle, shape)
    # The second turn supplies only the missing action when possible. Observed
    # provenance must accumulate within this thread, not reset between turns.
    complement = {"search": "openPage", "openPage": "search"}
    corrected = limited_turn(value, complement[missing]) if missing != "both" else FakeTurn(value)
    fake_sdk.turns = [limited_turn(value, missing), corrected]
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "synthetic", tmp_path / "job"
    )
    assert json.loads(text) == value
    assert searched and opened == {"https://example.com/evidence"}
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 2
    correction = fake_sdk.prompts[1]
    assert correction["unverified_urls"] == []
    assert correction["missing_approval_actions"] == (
        ["search", "openPage"] if missing == "both" else [missing]
    )
    assert "passed=false" in correction["task"] and "HOLD" in correction["task"]
    assert "实际" in correction["task"] and "web search" in correction["task"]
    assert fake_sdk.closed


@pytest.mark.parametrize("shape", ["editor", "review"])
async def test_correction_may_honestly_hold_without_inventing_research(
    tmp_path, fake_sdk, bundle, shape
):
    held = approval(bundle, shape, passed=False)
    fake_sdk.turns = [
        FakeTurn(approval(bundle, shape), research=False),
        FakeTurn(held, research=False),
    ]
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "synthetic", tmp_path / "job"
    )
    assert json.loads(text) == held and not opened and not searched
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 2
    if shape == "editor":
        assert not editor._result(text, [], opened, searched).review["passed"]


@pytest.mark.parametrize("shape", ["editor", "review"])
@pytest.mark.parametrize("missing", ["search", "openPage", "both"])
async def test_unsupported_second_pass_does_not_get_a_third_turn(
    tmp_path, fake_sdk, bundle, shape, missing
):
    value = approval(bundle, shape)
    fake_sdk.turn = limited_turn(value, missing)
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "synthetic", tmp_path / "job"
    )
    assert json.loads(text) == value
    assert editor._unobserved_approval_actions(text, opened, searched)
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 2
    # Execute never fabricates successful actions. The existing editor parser
    # still converts this unsupported claimed pass to HOLD after correction.
    if shape == "editor":
        result = editor._result(text, [], opened, searched)
        assert not result.review["passed"]
        assert any("HOLD" in finding for finding in result.review["findings"])


@pytest.mark.parametrize("missing", ["search", "openPage", "both"])
async def test_independent_review_still_holds_an_unsupported_corrected_pass(
    tmp_path, fake_sdk, bundle, missing
):
    fake_sdk.turn = limited_turn(approval(bundle, "review"), missing)
    store = Store(tmp_path / "store.sqlite3", "mock")
    definition = parse_definition(
        {"version": 1, "id": "synthetic", "nodes": [{"id": "review", "type": "review"}]}
    )
    nodes = EditorialNodes(store, definition, live_editor(tmp_path), tmp_path)
    context = NodeContext(
        run_id="synthetic-run",
        node_id="review",
        item_id="",
        params={},
        inputs={},
        run_inputs={"issue_date": "2026-09-06", "policy": {"editorial.md": "Synthetic only"}},
    )
    try:
        result = await nodes.review(
            context,
            tmp_path / "job",
            {"draft": bundle["draft"], "packets": [], "review": bundle["review"]},
        )
    finally:
        store.close()
    assert not result["review"]["passed"]
    assert any("HOLD" in finding for finding in result["review"]["findings"])
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 2


@pytest.mark.parametrize("corrected_search", [True, False])
async def test_url_and_approval_share_one_correction_budget(
    tmp_path, fake_sdk, bundle, packet, corrected_search
):
    bundle["supplemental_packets"] = [{"id": "supplement-1", "content": packet["content"]}]
    corrected = FakeTurn(bundle) if corrected_search else limited_turn(bundle, "search")
    fake_sdk.turns = [FakeTurn(bundle, research=False), corrected]
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "synthetic", tmp_path / "job"
    )
    correction = fake_sdk.prompts[1]
    assert correction["unverified_urls"] == ["https://example.com/evidence"]
    assert correction["missing_approval_actions"] == ["search", "openPage"]
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 2
    assert not editor._unopened_sources(text, opened)
    assert searched is corrected_search
    assert editor._result(text, [], opened, searched).review["passed"] is corrected_search


@pytest.mark.parametrize("shape", ["editor", "review"])
async def test_honest_initial_hold_does_not_force_actions(tmp_path, fake_sdk, bundle, shape):
    value = approval(bundle, shape, passed=False)
    fake_sdk.turn = FakeTurn(value, research=False)
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "synthetic", tmp_path / "job"
    )
    assert json.loads(text) == value and not opened and not searched
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 1


async def test_honest_hold_still_corrects_new_unopened_sources(tmp_path, fake_sdk, bundle, packet):
    value = approval(bundle, "editor", passed=False)
    value["supplemental_packets"] = [{"id": "supplement-1", "content": packet["content"]}]
    fake_sdk.turns = [FakeTurn(value, research=False), limited_turn(value, "search")]
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "synthetic", tmp_path / "job"
    )
    assert json.loads(text) == value and opened and not searched
    assert len(fake_sdk.prompts) == 2
    assert fake_sdk.prompts[1]["unverified_urls"] == ["https://example.com/evidence"]
    assert fake_sdk.prompts[1]["missing_approval_actions"] == []
    assert not editor._result(text, [], opened, searched).review["passed"]


@pytest.mark.parametrize("shape", ["editor", "review"])
async def test_action_correction_uses_original_timeout(tmp_path, fake_sdk, bundle, shape):
    value = approval(bundle, shape)
    hanging = FakeTurn(value, hang=True)
    fake_sdk.turns = [FakeTurn(value, research=False), hanging]
    with pytest.raises(editor.EditorError) as error:
        await live_editor(tmp_path, timeout_seconds=0.05).execute(
            "{}", {}, "synthetic", tmp_path / "job"
        )
    assert error.value.code == "timeout" and hanging.interrupted
    assert fake_sdk.thread_starts == 1 and len(fake_sdk.prompts) == 2
    assert fake_sdk.closed


@pytest.mark.parametrize(
    "value",
    [{}, {"passed": False}, {"passed": "true"}, {"review": {"passed": 1}}, {"review": None}],
)
def test_action_inspection_requires_an_exact_true_claim(value):
    assert editor._unobserved_approval_actions(json.dumps(value), set(), False) == []


def test_action_inspection_rejects_non_object():
    with pytest.raises(editor.EditorError) as error:
        editor._unobserved_approval_actions("[]", set(), False)
    assert error.value.code == "invalid_output"
