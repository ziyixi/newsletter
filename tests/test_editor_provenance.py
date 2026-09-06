"""Offline URL provenance regressions; no SDK, redirects, or network requests."""

import json

import pytest
from test_editor import FakeTurn, live_editor
from test_editor import fake_sdk as fake_sdk

from newsletter.contracts import validate_draft
from newsletter.editor import EditorError, _result, _unobserved_approval_actions

SHORT_URL = "https://example.org/article/synthetic-123"
CANONICAL_URL = "https://example.org/article/synthetic-news-story-synthetic-123"


@pytest.fixture
def bundle():
    # The same small packet/draft shape as the editor fixtures, with public
    # example URLs and conspicuously synthetic content rather than live data.
    return {
        "draft": {
            "subject": "Synthetic provenance fixture",
            "title": "Synthetic provenance fixture",
            "sections": [
                {
                    "kind": "feature",
                    "heading": "Synthetic statement",
                    "paragraphs": [
                        {"text": "Synthetic evidence only.", "citations": ["supplement-1/s1"]}
                    ],
                }
            ],
        },
        "review": {"passed": True, "findings": ["Synthetic review only."]},
        "supplemental_packets": [
            {
                "id": "supplement-1",
                "content": {
                    "title": "Synthetic source packet",
                    "body": "Synthetic fixture, not a real news report.",
                    "sources": [
                        {
                            "id": "s1",
                            "title": "Synthetic source",
                            "url": CANONICAL_URL,
                            "excerpt": "Synthetic evidence only.",
                            "access_scope": "full_text",
                        }
                    ],
                    "tags": ["fixture"],
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("source_url", "other_url"),
    [(CANONICAL_URL, SHORT_URL), (SHORT_URL, CANONICAL_URL)],
)
def test_same_host_and_content_id_do_not_prove_exact_source_was_opened(
    bundle, source_url, other_url
):
    bundle["supplemental_packets"][0]["content"]["sources"][0]["url"] = source_url
    text = json.dumps(bundle)
    with pytest.raises(EditorError) as error:
        _result(text, [], {other_url}, searched=True)
    assert error.value.code == "invalid_output"

    # A possible redirect/canonical relationship is not evidence. Only after
    # the exact cited URL also appears in the observed opens can it be accepted.
    result = _result(text, [], {other_url, source_url}, searched=True)
    assert result.review["passed"] is True
    added = result.supplemental_packets[0]
    assert added["content"]["sources"][0]["url"] == source_url
    assert result.draft["sections"][0]["paragraphs"][0]["citations"] == [added["id"] + "/s1"]
    validate_draft(result.draft, result.supplemental_packets)


@pytest.mark.parametrize(
    ("source_url", "opened_url"),
    [
        (CANONICAL_URL + "#table-1", CANONICAL_URL),
        (CANONICAL_URL + "#different-section", CANONICAL_URL),
        (CANONICAL_URL + "?edition=first#table-1", CANONICAL_URL + "?edition=first"),
    ],
)
def test_fragment_is_the_only_ignored_url_component(bundle, source_url, opened_url):
    bundle["supplemental_packets"][0]["content"]["sources"][0]["url"] = source_url
    # _collect already removes fragments from observed opens before _result.
    result = _result(json.dumps(bundle), [], {opened_url}, searched=True)
    assert result.review["passed"] is True
    assert result.supplemental_packets[0]["content"]["sources"][0]["url"] == source_url
    validate_draft(result.draft, result.supplemental_packets)


@pytest.mark.parametrize(
    ("source_suffix", "opened_suffix"),
    [
        ("?edition=first", ""),
        ("", "?edition=first"),
        ("?edition=first", "?edition=second"),
        ("?edition=first#table-1", "?edition=second"),
        ("?edition=first&view=full", "?view=full&edition=first"),
    ],
)
def test_query_parameters_are_not_removed_or_normalized(bundle, source_suffix, opened_suffix):
    bundle["supplemental_packets"][0]["content"]["sources"][0]["url"] = (
        CANONICAL_URL + source_suffix
    )
    with pytest.raises(EditorError) as error:
        _result(json.dumps(bundle), [], {CANONICAL_URL + opened_suffix}, searched=True)
    assert error.value.code == "invalid_output"


def test_reading_supporting_citations_receive_the_same_host_owned_packet_identity(bundle):
    supplement = bundle["supplemental_packets"][0]
    supplement["content"]["sources"].append(
        {
            **supplement["content"]["sources"][0],
            "id": "journal",
            "url": SHORT_URL,
        }
    )
    bundle["draft"]["recommended_reading"] = {
        "citation": "supplement-1/s1",
        "reason": "Synthetic primary reading and journal record.",
        "supporting_citations": ["supplement-1/journal"],
    }
    result = _result(json.dumps(bundle), [], {CANONICAL_URL, SHORT_URL}, searched=True)
    identity = result.supplemental_packets[0]["id"]
    reading = result.draft["recommended_reading"]
    assert identity != "supplement-1"
    assert reading["citation"] == identity + "/s1"
    assert reading["supporting_citations"] == [identity + "/journal"]
    validate_draft(result.draft, result.supplemental_packets)


@pytest.mark.parametrize("component", ["body", "reading", "chart", "signal"])
@pytest.mark.parametrize(
    "opened,searched,expected",
    [
        (set(), False, ["search", "openPage"]),
        ({SHORT_URL}, False, ["search"]),
        (set(), True, ["openPage"]),
        ({SHORT_URL}, True, []),
    ],
)
def test_component_approval_selects_only_missing_observed_actions(
    component, opened, searched, expected
):
    value = {
        "assessments": [{"component": component, "status": "approved", "findings": []}],
        "issues": [],
    }
    assert _unobserved_approval_actions(json.dumps(value), opened, searched) == expected


@pytest.mark.parametrize(
    "assessments",
    [
        [],
        None,
        "approved",
        {"component": "body", "status": "approved"},
        [{"component": "body", "status": "blocked"}],
        [{"component": "body", "status": "not_present"}],
        [{"component": "body", "status": True}],
        [{"component": "body", "status": "APPROVED"}],
        [{"component": "invented", "status": "approved"}],
        [{"component": [], "status": "approved"}],
        [None, "approved"],
    ],
)
def test_honest_component_hold_or_malformed_claim_does_not_trigger_research(assessments):
    assert (
        _unobserved_approval_actions(json.dumps({"assessments": assessments}), set(), False) == []
    )


async def test_component_approval_gets_one_same_thread_source_action_correction(tmp_path, fake_sdk):
    value = {
        "assessments": [{"component": "body", "status": "approved", "findings": []}],
        "issues": [],
    }
    fake_sdk.turns = [FakeTurn(value, research=False), FakeTurn(value)]
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "fixture", tmp_path / "job"
    )
    assert json.loads(text) == value and opened and searched
    assert len(fake_sdk.prompts) == 2 and fake_sdk.thread_starts == 1
    correction = fake_sdk.prompts[1]
    assert correction["missing_approval_actions"] == ["search", "openPage"]
    assert "status" in correction["task"] and "blocked" in correction["task"]
    assert "不得增加 passed 字段" in correction["task"]


async def test_second_component_self_approval_never_fabricates_actions_or_third_turn(
    tmp_path, fake_sdk
):
    value = {
        "assessments": [{"component": "signal", "status": "approved", "findings": []}],
        "issues": [],
    }
    fake_sdk.turn = FakeTurn(value, research=False)
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "fixture", tmp_path / "job"
    )
    assert not opened and not searched and len(fake_sdk.prompts) == 2
    # The StoryEditor receipt boundary still rejects this unobserved approval.
    assert _unobserved_approval_actions(text, opened, searched) == ["search", "openPage"]


async def test_all_components_blocked_do_not_spend_an_action_correction(tmp_path, fake_sdk):
    value = {
        "assessments": [{"component": "body", "status": "blocked", "findings": ["Cannot confirm"]}],
        "issues": [],
    }
    fake_sdk.turn = FakeTurn(value, research=False)
    text, opened, searched = await live_editor(tmp_path).execute(
        "{}", {}, "fixture", tmp_path / "job"
    )
    assert json.loads(text) == value and not opened and not searched
    assert len(fake_sdk.prompts) == 1


def test_exact_prior_retraction_claim_needs_fresh_actions_even_without_new_body_approval():
    value = {
        "assessments": [{"component": "body", "status": "not_present", "findings": []}],
        "prior_withdrawal": {"target_body_hash": "a" * 64},
    }
    assert _unobserved_approval_actions(json.dumps(value), set(), False) == ["search", "openPage"]
    assert _unobserved_approval_actions(json.dumps(value), {SHORT_URL}, True) == []
    value["prior_withdrawal"] = None
    assert _unobserved_approval_actions(json.dumps(value), set(), False) == []
