"""Local component failures never erase an independently approved story unit."""

import asyncio
import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from newsletter.contracts import SECTION_KINDS, ContractError, content_hash
from newsletter.editor import CodexEditor
from newsletter.errors import EditorError
from newsletter.workflow.publication import validate_result
from newsletter.workflow.story_editor import (
    _CHART_GUIDANCE,
    _WRITING_GUIDANCE,
    COMPONENTS,
    StoryEditor,
    body_content,
    story_review_schema,
    story_writer_schema,
)

URL = "https://example.com/research"
SECOND_URL = "https://example.com/publication"


def story(
    text="离线虚构事件发生；不是真实报道。", *, reading=False, chart=False
):
    value = {
        "story_id": "story-a",
        "title": "虚构事件的已知事实",
        "kind": "feature",
        "paragraphs": [{"text": text, "citations": ["packet/source"]}],
        "limitations": "仅离线fixture，不能真实发送。",
    }
    if reading:
        value["recommended_reading"] = {
            "citation": "packet/source",
            "reason": "离线方法、结果及边界。",
            "supporting_citations": ["packet/publication"],
        }
    if chart:
        value["chart"] = {
            "kind": "bar",
            "question": "虚构两组如何不同？",
            "metric": "虚构观测",
            "unit": "fixture",
            "period": "无真实时间范围",
            "caption": "不是研究结果",
            "alt_text": "虚构对比",
            "limitations": "仅测试",
            "points": [
                {
                    "label": "A",
                    "decimal_value": "1",
                    "citations": ["packet/source"],
                },
                {
                    "label": "B",
                    "decimal_value": "2",
                    "citations": ["packet/source"],
                },
            ],
        }
    return value


def writer(content=None, signal=None, supplements=None):
    return {
        "content": content,
        "signal": signal,
        "supplemental_packets": supplements or [],
    }


def review(
    *,
    body="approved",
    signal="not_present",
    reading="not_present",
    chart="not_present",
    issues=None,
    prior_withdrawal=None,
):
    statuses = {
        "body": body,
        "signal": signal,
        "reading": reading,
        "chart": chart,
    }
    return {
        "assessments": [
            {
                "component": name,
                "status": statuses[name],
                "findings": ["fixture finding"]
                if statuses[name] == "blocked"
                else [],
            }
            for name in COMPONENTS
        ],
        "issues": issues or [],
        "prior_withdrawal": prior_withdrawal,
    }


@pytest.fixture
def rig(tmp_path, monkeypatch):
    packet_body = {
        "title": "离线材料",
        "body": "虚构事件和观测，不得发送。",
        "tags": ["fixture"],
        "sources": [
            {
                "id": name,
                "title": "虚构来源",
                "url": url,
                "excerpt": "fixture excerpt",
                "access_scope": "full_text",
                "published_at": "",
            }
            for name, url in (("source", URL), ("publication", SECOND_URL))
        ],
    }
    packet = {
        "id": "packet",
        "content": packet_body,
        "workflow_id": "fixture",
        "producer_id": "fixture",
        "content_hash": content_hash(packet_body),
        "created_at": "2026-09-06T00:00:00Z",
        "is_fixture": True,
    }
    state = SimpleNamespace(replies=[], calls=[], checkpoints=[], packet=packet)

    async def execute(
        editor,
        prompt,
        schema,
        instructions,
        workspace,
        *,
        approval_sources=None,
    ):
        state.calls.append(
            {
                "prompt": json.loads(prompt),
                "schema": schema,
                "instructions": instructions,
                "path": workspace,
                "approval_sources": approval_sources,
            }
        )
        assert state.replies, "No unbounded retry or unexpected model call"
        response = state.replies.pop(0)
        if isinstance(response, BaseException):
            raise response
        value, opened, searched = response
        return (
            value if isinstance(value, str) else json.dumps(value),
            opened,
            searched,
        )

    monkeypatch.setattr(CodexEditor, "execute", execute)
    state.editor = StoryEditor(CodexEditor(tmp_path / "unused-auth"))

    async def run(**overrides):
        kwargs = {
            "task": {"id": "story-a", "question": "虚构事件"},
            "candidates": [],
            "packets": [deepcopy(packet)],
            "issue_date": "2026-09-06",
            "policy": {
                "editorial.md": "Fixture policy",
                "reader-profile.md": "Fixture reader",
            },
            "workspace": tmp_path / "job",
            "mode": "brief",
            "is_fixture": True,
            "on_checkpoint": state.checkpoints.append,
            **overrides,
        }
        return await state.editor.prepare(**kwargs)

    state.run = run
    return state


def reply(value, *, opened=None, searched=True):
    return value, {URL, SECOND_URL} if opened is None else opened, searched


async def test_approved_body_and_signal_freeze_without_repair(rig):
    content, signal = story(), story("仅确认虚构事件；更多细节仍在核验。")
    rig.replies = [
        reply(writer(content, signal)),
        reply(review(signal="approved")),
    ]
    result = await rig.run()
    assert result["content"] == content and result["signal"] == signal
    assert result["reason"] == "approved" and len(rig.calls) == 2
    assert rig.checkpoints == [result]
    assert result["provenance"]["packets_hash"] == content_hash(
        result["packets"]
    )
    for assessment in result["assessments"]:
        assert UUID(assessment["writer_job_id"]) != UUID(
            assessment["reviewer_job_id"]
        )
        assert assessment["opened"] is True and assessment["searched"] is True
    assert len({call["path"] for call in rig.calls}) == 2
    assert all(call["path"].is_dir() for call in rig.calls)
    validate_result(result)


async def test_card_and_chart_can_be_discarded_without_body_repair(rig):
    content = story(reading=True, chart=True)
    rig.replies = [
        reply(writer(content)),
        reply(review(reading="blocked", chart="blocked")),
    ]
    result = await rig.run(mode="deep")
    assert result["content"] == body_content(content)
    assert len(rig.calls) == 2 and result["reason"] == "approved"
    receipt = next(a for a in result["assessments"] if a["component"] == "body")
    assert receipt["content_hash"] == content_hash(body_content(content))
    validate_result(result)


async def test_every_optional_component_has_its_own_hash_and_source_observation(
    rig,
):
    content = story(reading=True, chart=True)
    rig.replies = [
        reply(writer(content)),
        reply(review(reading="approved", chart="approved")),
    ]
    result = await rig.run(mode="deep")
    assert result["content"] == content
    expected = {
        "body": body_content(content),
        "reading": content["recommended_reading"],
        "chart": content["chart"],
    }
    for item in result["assessments"]:
        if item["component"] in expected:
            assert item["content_hash"] == content_hash(
                expected[item["component"]]
            )
    validate_result(result)


async def test_reading_supporting_source_must_be_reopened_even_when_primary_was_opened(
    rig,
):
    content = story(reading=True)
    rig.replies = [
        reply(writer(content)),
        reply(review(reading="approved"), opened={URL}),
    ]
    result = await rig.run(mode="deep")
    assert result["content"] == body_content(content) and len(rig.calls) == 2
    assert (
        next(a for a in result["assessments"] if a["component"] == "reading")[
            "status"
        ]
        == "blocked"
    )


@pytest.mark.parametrize(
    "optional",
    [
        {
            "recommended_reading": {
                "citation": "packet/missing",
                "reason": "invalid",
                "supporting_citations": [],
            }
        },
        {
            "recommended_reading": {
                "citation": ["bad"],
                "reason": "invalid",
                "supporting_citations": [],
            }
        },
        {"recommended_reading": "not an object"},
        {"chart": {"points": "not an array"}},
    ],
)
async def test_malformed_optional_component_never_invalidates_independent_body(
    rig, optional
):
    content = {**story(), **optional}
    rig.replies = [reply(writer(content)), reply(review())]
    result = await rig.run()
    assert result["content"] == story() and len(rig.calls) == 2
    assert result["issues"][0]["reason"].startswith(
        "component_contract_invalid:"
    )


async def test_bad_body_repairs_once_and_never_changes_approved_signal(rig):
    original, fixed, signal = (
        story(),
        story("修正后的虚构完整表述。"),
        story("虚构事件已确认。"),
    )
    rig.replies = [
        reply(writer(original, signal)),
        reply(review(body="blocked", signal="approved")),
        reply(writer(fixed)),
        reply(review()),
    ]
    result = await rig.run()
    assert result["content"] == fixed and result["signal"] == signal
    assert result["reason"] == "repaired" and len(rig.calls) == 4
    assert (
        rig.checkpoints[0]["content"] is None
        and rig.checkpoints[0]["signal"] == signal
    )
    assert rig.checkpoints[1] == result
    assert {a["round"] for a in result["assessments"]} == {"initial", "repair"}
    assert len({call["path"] for call in rig.calls}) == 4
    for checkpoint in rig.checkpoints:
        validate_result(checkpoint)


async def test_second_body_hold_keeps_signal_without_third_attempt(rig):
    signal = story("只确认事件存在。")
    rig.replies = [
        reply(writer(story(), signal)),
        reply(review(body="blocked", signal="approved")),
        reply(writer(story("修订仍不成立。"))),
        reply(review(body="blocked")),
    ]
    result = await rig.run()
    assert result["content"] is None and result["signal"] == signal
    assert result["reason"] == "confirmed_signal" and len(rig.calls) == 4


async def test_cancellation_after_signal_checkpoint_cannot_erase_approved_evidence(
    rig,
):
    rig.replies = [
        reply(writer(story(), story("最小事件。"))),
        reply(review(body="blocked", signal="approved")),
        asyncio.CancelledError(),
    ]
    with pytest.raises(asyncio.CancelledError):
        await rig.run()
    assert len(rig.checkpoints) == 1 and rig.checkpoints[0]["signal"] == story(
        "最小事件。"
    )
    assert rig.checkpoints[0]["content"] is None


@pytest.mark.parametrize(
    "error",
    [
        EditorError("authentication"),
        ContractError("BAD", "fixture"),
        RuntimeError("fixture storage failure"),
    ],
)
async def test_checkpoint_failure_propagates_without_another_model_call(
    rig, error
):
    rig.replies = [reply(writer(story())), reply(review())]

    def broken(_):
        raise error

    with pytest.raises(type(error)):
        await rig.run(on_checkpoint=broken)
    assert len(rig.calls) == 2


async def test_checkpoint_is_deep_copy_not_mutable_later_repair_state(rig):
    rig.replies = [
        reply(writer(story(), story("事件已知。"))),
        reply(review(body="blocked", signal="approved")),
        reply(writer(story("修订内容。"))),
        reply(review()),
    ]
    result = await rig.run()
    assert len(rig.checkpoints[0]["assessments"]) == 4
    result["signal"]["title"] = "caller mutation"
    assert rig.checkpoints[0]["signal"]["title"] != "caller mutation"


@pytest.mark.parametrize("stage", ["writer", "review", "repair"])
async def test_provider_failures_are_finite_and_never_promote_unverified_content(
    rig, stage
):
    signal = story("已核实最小事件。")
    rig.replies = {
        "writer": [EditorError("unavailable")],
        "review": [reply(writer(story(), signal)), EditorError("timeout")],
        "repair": [
            reply(writer(story(), signal)),
            reply(review(body="blocked", signal="approved")),
            EditorError("unavailable"),
        ],
    }[stage]
    result = await rig.run()
    assert result["content"] is None
    assert result["signal"] == (signal if stage == "repair" else None)
    assert result["issues"][-1]["round"] == "service"


async def test_deep_provider_failure_does_not_mislabel_or_mutate_prior_brief(
    rig,
):
    prior = {"content": story(), "signal": story("最小事件。")}
    frozen = deepcopy(prior)
    rig.replies = [EditorError("unavailable")]
    result = await rig.run(mode="deep", prior=prior)
    assert result["content"] is None and result["signal"] is None
    assert prior == frozen
    assert rig.calls[0]["prompt"]["prior_verified_brief_untrusted"] == prior
    validate_result(result)


@pytest.mark.parametrize(
    "opened,searched", [(set(), True), ({URL}, False), ({SECOND_URL}, True)]
)
async def test_missing_fresh_review_actions_block_even_model_self_approval(
    rig, opened, searched
):
    rig.replies = [
        reply(writer(story())),
        reply(review(), opened=opened, searched=searched),
        reply(writer(story())),
        reply(review(), opened=opened, searched=searched),
    ]
    result = await rig.run()
    assert result["content"] is None and len(rig.calls) == 4
    assert all(a["status"] != "approved" for a in result["assessments"])


async def test_metadata_is_not_a_substitute_for_reading_evidence(rig):
    rig.packet["content"]["sources"][0]["access_scope"] = "metadata"
    rig.replies = [
        reply(writer(story())),
        reply(review()),
        reply(writer(story())),
        reply(review()),
    ]
    result = await rig.run()
    assert result["content"] is None


async def test_contradictory_approved_with_unresolved_issue_is_not_accepted(
    rig,
):
    issue = {
        "component": "body",
        "claim": "数字",
        "reason": "数字错误",
        "evidence": ["packet/source"],
        "action": "correct",
    }
    rig.replies = [
        reply(writer(story())),
        reply(review(issues=[issue])),
        reply(writer(story())),
        reply(review(body="blocked")),
    ]
    result = await rig.run()
    assert result["content"] is None and len(rig.calls) == 4


async def test_new_sources_are_opened_normalized_and_all_reference_locations_remapped(
    rig,
):
    content = story(reading=True, chart=True)
    content["paragraphs"][0]["citations"] = ["supplement-1/source"]
    content["recommended_reading"]["citation"] = "supplement-1/source"
    content["recommended_reading"]["supporting_citations"] = [
        "supplement-1/publication"
    ]
    content["chart"]["points"][0]["citations"] = ["supplement-1/source"]
    supplement = {
        "id": "supplement-1",
        "content": deepcopy(rig.packet["content"]),
    }
    rig.replies = [
        reply(writer(content, supplements=[supplement])),
        reply(review(reading="approved", chart="approved")),
    ]
    result = await rig.run(mode="deep")
    generated = result["packets"][-1]
    UUID(generated["id"])
    assert generated["is_fixture"] is True and generated[
        "content_hash"
    ] == content_hash(generated["content"])
    serialized = json.dumps(result["content"])
    assert "supplement-1/" not in serialized and generated["id"] in serialized
    assert (
        generated["id"] + "/publication"
        in result["content"]["recommended_reading"]["supporting_citations"]
    )
    validate_result(result)


async def test_real_story_can_start_with_candidates_and_no_preexisting_packets(
    rig,
):
    content = story()
    content["paragraphs"][0]["citations"] = ["supplement-1/source"]
    supplement = {
        "id": "supplement-1",
        "content": deepcopy(rig.packet["content"]),
    }
    rig.replies = [
        reply(writer(content, supplements=[supplement])),
        reply(review()),
    ]
    result = await rig.run(packets=[], is_fixture=False)
    assert result["content"] is not None and len(result["packets"]) == 1
    assert result["packets"][0]["is_fixture"] is False
    validate_result(result)


async def test_new_sources_without_actual_open_cannot_be_used(rig):
    supplement = {
        "id": "supplement-1",
        "content": deepcopy(rig.packet["content"]),
    }
    rig.replies = [
        reply(writer(story(), supplements=[supplement]), opened={URL})
    ]
    result = await rig.run()
    assert result["content"] is None and len(rig.calls) == 1
    assert len(result["packets"]) == 1


@pytest.mark.parametrize(
    "bad",
    [
        "not JSON",
        '{"content":null,"content":null,"signal":null,"supplemental_packets":[]}',
        {
            "content": None,
            "signal": None,
            "supplemental_packets": [],
            "private": "unsupported",
        },
    ],
)
async def test_malformed_model_envelope_is_never_published(rig, bad):
    rig.replies = [reply(bad)]
    result = await rig.run()
    assert (
        result["content"] is None
        and result["signal"] is None
        and len(rig.calls) == 1
    )


async def test_malformed_body_can_still_leave_independently_checked_signal(rig):
    bad = story()
    bad["paragraphs"][0]["citations"] = ["packet/missing"]
    rig.replies = [
        reply(writer(bad, story("事件存在。"))),
        reply(review(body="not_present", signal="approved")),
        reply(writer(bad)),
    ]
    result = await rig.run()
    assert result["content"] is None and result["signal"] == story("事件存在。")
    assert len(rig.calls) == 3
    assert rig.checkpoints[0]["signal"] == story("事件存在。")


async def test_unconfirmed_event_produces_no_signal_and_no_fabricated_body(rig):
    rig.replies = [reply(writer()), reply(review(body="not_present"))]
    result = await rig.run()
    assert result["content"] is None and result["signal"] is None
    assert result["reason"] == "withheld" and not rig.checkpoints


@pytest.mark.parametrize("mode,count", [("brief", 3), ("deep", 17)])
async def test_text_bounds_do_not_cut_paragraphs_into_unreviewed_fragments(
    rig, mode, count
):
    content = story()
    content["paragraphs"] *= count
    rig.replies = [reply(writer(content)), reply(review(body="not_present"))]
    result = await rig.run(mode=mode)
    assert result["content"] is None


async def test_signal_cannot_carry_optional_cards_or_unchecked_two_paragraphs(
    rig,
):
    signal = story(reading=True)
    rig.replies = [reply(writer(story(), signal)), reply(review())]
    result = await rig.run()
    assert result["content"] == story() and result["signal"] is None


async def test_deep_cannot_rewrite_verified_fallback_signal(rig):
    rig.replies = [reply(writer(story(), story("new signal")))]
    result = await rig.run(mode="deep")
    assert result["content"] is None and result["signal"] is None


async def test_present_component_marked_absent_is_blocked_not_silently_approved(
    rig,
):
    rig.replies = [
        reply(writer(story())),
        reply(review(body="not_present")),
        reply(writer(story())),
        reply(review(body="blocked")),
    ]
    result = await rig.run()
    assert result["content"] is None and len(rig.calls) == 4


async def test_duplicate_component_review_cannot_omit_another_component(rig):
    bad = review()
    bad["assessments"][1] = deepcopy(bad["assessments"][0])
    rig.replies = [reply(writer(story())), reply(bad)]
    result = await rig.run()
    assert result["content"] is None and len(rig.calls) == 2


async def test_title_and_limitations_are_bound_into_body_receipt(rig):
    rig.replies = [reply(writer(story())), reply(review())]
    result = await rig.run()
    original_hash = next(
        a["content_hash"]
        for a in result["assessments"]
        if a["component"] == "body"
    )
    for key in ("title", "limitations"):
        modified = deepcopy(result["content"])
        modified[key] += " altered"
        assert content_hash(body_content(modified)) != original_hash


def test_model_schema_derives_public_story_fields_and_multiple_reading_sources():
    schema = story_writer_schema()
    fields = schema["properties"]["content"]["anyOf"][0]["properties"]
    assert (
        "supporting_citations"
        in fields["recommended_reading"]["anyOf"][0]["properties"]
    )
    assert set(fields) == {
        "story_id",
        "title",
        "kind",
        "paragraphs",
        "limitations",
        "recommended_reading",
        "chart",
    }
    assert fields["kind"]["enum"] == list(SECTION_KINDS)
    assert set(story_review_schema()["properties"]) == {
        "assessments",
        "issues",
        "prior_withdrawal",
    }


@pytest.mark.parametrize(
    "mode,repair,paragraph_limit",
    [
        ("brief", False, 2),
        ("brief", True, 2),
        ("deep", False, 16),
        ("deep", True, 16),
    ],
)
def test_writer_schema_matches_runtime_mode_and_signal_bounds(
    mode, repair, paragraph_limit
):
    properties = story_writer_schema(mode, repair=repair)["properties"]
    content = properties["content"]["anyOf"][0]["properties"]
    assert content["paragraphs"]["maxItems"] == paragraph_limit
    if mode == "brief" and not repair:
        signal = properties["signal"]["anyOf"][0]["properties"]
        assert signal["paragraphs"]["maxItems"] == 1
        assert (
            signal["chart"] == signal["recommended_reading"] == {"type": "null"}
        )
    else:
        assert properties["signal"] == {"type": "null"}


async def test_mode_specific_schema_is_used_in_initial_and_repair_jobs(rig):
    rig.replies = [
        reply(writer(story())),
        reply(review(body="blocked")),
        reply(writer(story())),
        reply(review()),
    ]
    await rig.run(mode="brief")
    first, repair = (
        rig.calls[0]["schema"]["properties"],
        rig.calls[2]["schema"]["properties"],
    )
    assert (
        first["content"]["anyOf"][0]["properties"]["paragraphs"]["maxItems"]
        == 2
    )
    assert "anyOf" in first["signal"] and repair["signal"] == {"type": "null"}


@pytest.mark.parametrize(
    "override",
    [{"task": {"id": "bad/id"}}, {"mode": "unknown"}, {"is_fixture": "false"}],
)
async def test_unsafe_input_is_rejected_before_model(rig, override):
    with pytest.raises(EditorError, match="invalid input"):
        await rig.run(**override)
    assert not rig.calls


@pytest.mark.parametrize(
    "code", ["authentication", "configuration", "rate_limit"]
)
@pytest.mark.parametrize("stage", ["writer", "review", "repair"])
async def test_account_level_failure_propagates_to_stop_following_model_jobs(
    rig, code, stage
):
    prefix = {
        "writer": [],
        "review": [reply(writer(story()))],
        "repair": [
            reply(writer(story(), story("事件本身已有证据。"))),
            reply(review(body="blocked", signal="approved")),
        ],
    }[stage]
    rig.replies = [*prefix, EditorError(code)]
    with pytest.raises(EditorError) as error:
        await rig.run()
    assert error.value.code == code
    assert len(rig.calls) == len(prefix) + 1
    assert len(rig.checkpoints) == (1 if stage == "repair" else 0)


async def verified_prior(rig):
    rig.replies = [
        reply(writer(story(), story("独立确认的最小事件描述。"))),
        reply(review(signal="approved")),
    ]
    prior = await rig.run()
    rig.calls.clear()
    rig.checkpoints.clear()
    return prior


def withdrawal(prior, **changes):
    return {
        "target_body_hash": content_hash(body_content(prior["content"])),
        "affected_signal_hash": "",
        "claim": prior["content"]["paragraphs"][0]["text"],
        "reason": "离线fixture新来源明确否定旧数字，测试精确撤回而非缺少研究。",
        "evidence": ["packet/publication"],
        **changes,
    }


async def test_deep_review_can_withdraw_exact_disproved_brief_without_extra_invocation(
    rig,
):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer(story("新证据支持的独立完整报道。"))),
        reply(review(prior_withdrawal=withdrawal(prior))),
    ]
    result = await rig.run(mode="deep", prior=prior, packets=prior["packets"])
    assert len(rig.calls) == 2 and result["content"] is not None
    item = result["withdrawals"][0]
    assert item["content_hash"] == content_hash(body_content(prior["content"]))
    assert item["affected_signal_hash"] == "" and item["mode"] == "brief"
    assert item["reviewer_job_id"] in {
        r["reviewer_job_id"] for r in result["assessments"]
    }
    assert rig.calls[1]["prompt"]["prior_verified_brief_untrusted"] == prior
    assert rig.checkpoints == [result]
    validate_result(result)


async def test_withdrawal_only_is_checkpointed_even_when_new_deep_body_is_unavailable(
    rig,
):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer()),
        reply(review(body="not_present", prior_withdrawal=withdrawal(prior))),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert result["content"] is None and result["signal"] is None
    assert len(result["withdrawals"]) == 1 and rig.checkpoints == [result]
    assert len(rig.calls) == 2
    validate_result(result)


async def test_withdrawal_survives_later_deep_repair_cancellation(rig):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer(story("新深读尚未正确，不可替代旧文。"))),
        reply(review(body="blocked", prior_withdrawal=withdrawal(prior))),
        asyncio.CancelledError(),
    ]
    with pytest.raises(asyncio.CancelledError):
        await rig.run(mode="deep", prior=prior)
    assert len(rig.checkpoints) == 1 and rig.checkpoints[0]["withdrawals"]
    assert rig.checkpoints[0]["content"] is None
    validate_result(rig.checkpoints[0])


async def test_review_can_explicitly_bind_the_same_error_in_paraphrased_signal(
    rig,
):
    prior = await verified_prior(rig)
    proposal = withdrawal(
        prior, affected_signal_hash=content_hash(prior["signal"])
    )
    rig.replies = [
        reply(writer()),
        reply(review(body="not_present", prior_withdrawal=proposal)),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert result["withdrawals"][0]["affected_signal_hash"] == content_hash(
        prior["signal"]
    )
    validate_result(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"target_body_hash": "0" * 64},
        {"claim": "too short"},
        {"claim": "这一段根本不是任何旧简讯的逐字摘录。"},
        {"reason": ""},
        {"reason": " "},
        {"evidence": []},
        {"evidence": ["packet/missing"]},
        {"evidence": ["packet/publication", "packet/publication"]},
        {"affected_signal_hash": "0" * 64},
        {"affected_signal_hash": None},
    ],
)
async def test_unbound_or_unsubstantiated_withdrawal_does_not_remove_prior_or_new_body(
    rig, changes
):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer(story())),
        reply(review(prior_withdrawal=withdrawal(prior, **changes))),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert "withdrawals" not in result and result["content"] is not None
    assert any(
        issue["reason"] == "invalid_prior_withdrawal"
        for issue in result["issues"]
    )
    validate_result(result)


@pytest.mark.parametrize(
    "opened,searched",
    [({URL}, True), ({URL, SECOND_URL}, False), (set(), True)],
)
async def test_prior_withdrawal_requires_fresh_open_of_its_specific_evidence(
    rig, opened, searched
):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer()),
        reply(
            review(body="not_present", prior_withdrawal=withdrawal(prior)),
            opened=opened,
            searched=searched,
        ),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert "withdrawals" not in result and not rig.checkpoints


async def test_metadata_evidence_cannot_withdraw_an_independently_approved_brief(
    rig,
):
    prior = await verified_prior(rig)
    rig.packet["content"]["sources"][1]["access_scope"] = "metadata"
    rig.packet["content_hash"] = content_hash(rig.packet["content"])
    rig.replies = [
        reply(writer()),
        reply(review(body="not_present", prior_withdrawal=withdrawal(prior))),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert "withdrawals" not in result


@pytest.mark.parametrize(
    "mutation", ["other_story", "tampered_receipt", "not_brief"]
)
async def test_withdrawal_requires_a_genuinely_bound_prior_brief(rig, mutation):
    prior = await verified_prior(rig)
    if mutation == "other_story":
        prior["story_id"] = "other-story"
    elif mutation == "tampered_receipt":
        prior["assessments"][0]["searched"] = False
    else:
        prior["mode"] = "deep"
    rig.replies = [
        reply(writer()),
        reply(review(body="not_present", prior_withdrawal=withdrawal(prior))),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert "withdrawals" not in result
    assert len(rig.calls) == 1


async def test_ordinary_deep_hold_never_implicitly_withdraws_verified_brief(
    rig,
):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer(story())),
        reply(review(body="blocked")),
        reply(writer(story())),
        reply(review(body="blocked")),
    ]
    result = await rig.run(mode="deep", prior=prior)
    assert result["content"] is None and "withdrawals" not in result
    assert rig.calls[-1]["prompt"]["prior_verified_brief_untrusted"] is None


async def test_brief_stage_cannot_issue_a_prior_withdrawal(rig):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer(story())),
        reply(review(prior_withdrawal=withdrawal(prior))),
    ]
    result = await rig.run(mode="brief", prior=prior)
    assert "withdrawals" not in result and result["content"] is not None


async def test_review_receives_code_owned_component_urls_including_reading_support(
    rig,
):
    rig.replies = [
        reply(writer(story(reading=True, chart=True))),
        reply(review(reading="approved", chart="approved")),
    ]
    result = await rig.run(mode="deep")
    validate_result(result)
    expected = rig.calls[1]["approval_sources"]
    assert expected.components["body"] == [URL]
    assert expected.components["reading"] == [URL, SECOND_URL]
    assert expected.components["chart"] == [URL]
    assert expected.evidence == {} and rig.calls[0]["approval_sources"] is None


async def test_missing_url_diagnostic_identifies_exact_component_reference_and_url(
    rig,
):
    rig.replies = [
        reply(writer(story(reading=True))),
        reply(review(reading="approved"), opened={URL}),
    ]
    result = await rig.run(mode="deep")
    assert result["content"] == story() and len(rig.calls) == 2
    assert any(
        SECOND_URL in finding
        for assessment in result["assessments"]
        if assessment["component"] == "reading"
        for finding in assessment["findings"]
    )
    assert any(
        issue["component"] == "reading"
        and "missing_review_open_url" in issue["reason"]
        and issue["evidence"] == ["packet/publication"]
        for issue in result["issues"]
    )
    validate_result(result)


async def test_metadata_diagnostic_explains_actual_problem_to_repair_without_raising_scope(
    rig,
):
    rig.packet["content"]["sources"][0]["access_scope"] = "metadata"
    rig.replies = [
        reply(writer(story())),
        reply(review()),
        reply(writer(story())),
        reply(review()),
    ]
    result = await rig.run()
    assert result["content"] is None
    first = next(a for a in result["assessments"] if a["component"] == "body")
    assert any(
        "metadata_citations_not_publishable: packet/source" in finding
        for finding in first["findings"]
    )
    assert not any(
        "missing_review_open" in finding for finding in first["findings"]
    )
    repair = rig.calls[2]["prompt"]["repair_untrusted"]
    assert any(
        "metadata_citations_not_publishable" in issue["reason"]
        and issue["action"] == "remove"
        for issue in repair["issues"]
    )
    rules = rig.calls[0]["prompt"]["output_rules"]
    assert "不得为了过审把来源access_scope标高" in rules
    assert "必须另外写出1段最小signal" in rules
    assert "只有事件本身无法确认时signal才为null" in rules


async def test_missing_search_diagnostic_is_distinct_from_url_or_scope_problem(
    rig,
):
    rig.replies = [
        reply(writer(story())),
        reply(review(), searched=False),
        reply(writer(story())),
        reply(review(), searched=False),
    ]
    result = await rig.run()
    first = next(a for a in result["assessments"] if a["component"] == "body")
    assert any(
        "missing_review_search" in finding for finding in first["findings"]
    )
    assert not any(
        "missing_review_open" in finding or "metadata_citations" in finding
        for finding in first["findings"]
    )
    assert any(
        "missing_review_search" in issue["reason"]
        and issue["action"] == "research"
        for issue in result["issues"]
    )


async def test_only_deep_initial_review_receives_withdrawal_evidence_lookup(
    rig,
):
    prior = await verified_prior(rig)
    rig.replies = [
        reply(writer(story())),
        reply(review(body="blocked")),
        reply(writer(story())),
        reply(review()),
    ]
    await rig.run(mode="deep", prior=prior)
    assert rig.calls[1]["approval_sources"].evidence == {
        "packet/source": URL,
        "packet/publication": SECOND_URL,
    }
    assert rig.calls[3]["approval_sources"].evidence == {}


def test_schema_binds_current_story_id_exact_citations_and_excludes_metadata(
    rig,
):
    rig.packet["content"]["sources"][1]["access_scope"] = "metadata"
    schema = story_writer_schema(
        "brief", story_id="story-a", packets=[rig.packet]
    )
    props = schema["properties"]["content"]["anyOf"][0]["properties"]
    assert props["story_id"]["enum"] == ["story-a"]
    pattern = props["paragraphs"]["items"]["properties"]["citations"]["items"][
        "pattern"
    ]
    for ref in (
        "packet/source",
        "supplement-1/primary",
        "supplement-6/source-2",
    ):
        assert re.fullmatch(pattern, ref)
    for ref in (
        "packet/publication",
        "packet/missing",
        "wrong/source",
        "supplement-7/source",
        URL,
    ):
        assert not re.fullmatch(pattern, ref)
    signal = schema["properties"]["signal"]["anyOf"][0]["properties"]
    assert signal["story_id"]["enum"] == ["story-a"]
    assert (
        signal["paragraphs"]["items"]["properties"]["citations"]["items"][
            "pattern"
        ]
        == pattern
    )


def test_schema_text_and_chart_bounds_match_runtime_contract(rig):
    props = story_writer_schema("brief", packets=[rig.packet])["properties"][
        "content"
    ]["anyOf"][0]["properties"]
    assert (
        props["title"]["maxLength"] == 300
        and props["limitations"]["maxLength"] == 4000
    )
    paragraph = props["paragraphs"]["items"]["properties"]
    assert paragraph["text"]["maxLength"] == 8000
    assert paragraph["citations"]["minItems"] == 1
    assert "uniqueItems" not in paragraph["citations"]
    reading = props["recommended_reading"]["anyOf"][0]["properties"]
    assert reading["reason"]["maxLength"] == 1000
    assert reading["supporting_citations"]["maxItems"] == 31
    assert "uniqueItems" not in reading["supporting_citations"]
    chart = props["chart"]["anyOf"][0]["properties"]
    assert chart["points"]["maxItems"] == 32
    assert all(
        chart[key]["maxLength"] == 1000
        for key in (
            "question",
            "metric",
            "unit",
            "period",
            "caption",
            "alt_text",
        )
    )
    point = next(
        item["properties"]
        for item in chart["points"]["items"]["anyOf"]
        if "decimal_value" in item["properties"]
    )
    assert point["citations"]["minItems"] == 1
    for value in ("-2.3", "0", "5.9", "1e-3"):
        assert re.fullmatch(point["decimal_value"]["pattern"], value)
    for value in ("23%", "1,000", "NaN", "Infinity", "2万人"):
        assert not re.fullmatch(point["decimal_value"]["pattern"], value)


def test_supplement_source_and_body_schema_are_bounded_like_contract():
    props = story_writer_schema()["properties"]["supplemental_packets"][
        "items"
    ]["properties"]["content"]["properties"]
    assert props["body"]["maxLength"] == 65536
    assert (
        props["sources"]["minItems"] == 1 and props["sources"]["maxItems"] == 32
    )
    source = props["sources"]["items"]["properties"]
    assert (
        source["url"]["maxLength"] == 2048
        and source["excerpt"]["maxLength"] == 20000
    )


async def test_exact_duplicate_references_are_removed_without_changing_any_prose(
    rig,
):
    content = story(reading=True, chart=True)
    original = deepcopy(content)
    content["paragraphs"][0]["citations"] = ["packet/source", "packet/source"]
    content["recommended_reading"]["supporting_citations"] = [
        "packet/source",
        "packet/publication",
        "packet/publication",
    ]
    content["chart"]["points"][0]["citations"] *= 2
    rig.replies = [
        reply(writer(content)),
        reply(review(reading="approved", chart="approved")),
    ]
    result = await rig.run()
    assert result["content"] == original and len(rig.calls) == 2
    validate_result(result)


@pytest.mark.parametrize(
    "kind",
    [
        "world",
        "feature",
        "context",
        "ai_ml",
        "science",
        "economy",
        "technology",
        "health",
    ],
)
async def test_semantic_story_kind_survives_writer_validation_and_review(
    rig, kind
):
    content = story()
    content["kind"] = kind
    rig.replies = [reply(writer(content)), reply(review())]
    result = await rig.run()
    assert result["content"]["kind"] == kind
    validate_result(result)


async def test_writer_receives_current_task_schema_and_metadata_is_not_an_available_citation(
    rig,
):
    rig.packet["content"]["sources"][1]["access_scope"] = "metadata"
    rig.replies = [reply(writer(story())), reply(review())]
    result = await rig.run()
    assert result["content"] is not None
    assert rig.calls[0]["schema"]["properties"]["content"]["anyOf"][0][
        "properties"
    ]["story_id"]["enum"] == ["story-a"]
    assert rig.calls[0]["prompt"]["available_citations"] == ["packet/source"]


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("id", "story_id_mismatch"),
        ("long_title", "title exceeds its length limit"),
        ("paragraphs", "paragraph_count_outside_mode_limit"),
        ("no_citation", "paragraph_missing_citation"),
        ("unknown_citation", "INVALID_CITATION"),
    ],
)
async def test_invalid_body_gets_precise_safe_diagnostics_and_one_repair_before_independent_review(
    rig, mutation, expected
):
    content = story()
    if mutation == "id":
        content["story_id"] = "wrong-id"
    elif mutation == "long_title":
        content["title"] = "private-like-invalid-payload-" * 20
    elif mutation == "paragraphs":
        content["paragraphs"] *= 3
    elif mutation == "no_citation":
        content["paragraphs"][0]["citations"] = []
    else:
        content["paragraphs"][0]["citations"] = ["packet/missing"]
    rig.replies = [
        reply(writer(content)),
        reply(writer(story("经过修复并等待独审的正文。"))),
        reply(review()),
    ]
    result = await rig.run()
    assert result["reason"] == "repaired" and result["content"] is not None
    assert len(rig.calls) == 3 and len(rig.checkpoints) == 1
    assert expected in result["issues"][0]["reason"]
    assert (
        expected
        in rig.calls[1]["prompt"]["repair_untrusted"]["issues"][0]["reason"]
    )
    assert "private-like-invalid-payload" not in json.dumps(result)
    assert all(
        receipt["round"] == "repair" for receipt in result["assessments"]
    )
    validate_result(result)


async def test_malformed_signal_without_body_can_be_rewritten_as_a_new_independently_reviewed_brief(
    rig,
):
    malformed = story("仅用于测试的最小事件。")
    malformed["story_id"] = "wrong-id"
    rig.replies = [
        reply(writer(None, malformed)),
        reply(writer(story("格式修正后的简版事实。"))),
        reply(review()),
    ]
    result = await rig.run()
    assert result["reason"] == "repaired" and result["signal"] is None
    assert (
        rig.calls[1]["prompt"]["repair_untrusted"]["source_component"]
        == "signal"
    )
    assert len(rig.calls) == 3 and all(
        r["round"] == "repair" for r in result["assessments"]
    )
    validate_result(result)


async def test_second_malformed_signal_repair_never_gets_a_fake_approval_or_third_writer(
    rig,
):
    malformed = story()
    malformed["paragraphs"][0]["citations"] = ["unknown/source"]
    rig.replies = [reply(writer(None, malformed)), reply(writer(malformed))]
    result = await rig.run()
    assert result["content"] is None and result["signal"] is None
    assert (
        len(rig.calls) == 2
        and not result["assessments"]
        and not rig.checkpoints
    )
    assert (
        sum(
            "component_contract_invalid" in issue["reason"]
            for issue in result["issues"]
        )
        == 2
    )


async def test_valid_signal_is_checkpointed_before_malformed_body_repair_and_independent_review(
    rig,
):
    malformed = story()
    malformed["story_id"] = "wrong-id"
    signal = story("可独立核实的最小事件。")
    rig.replies = [
        reply(writer(malformed, signal)),
        reply(review(body="not_present", signal="approved")),
        reply(writer(story())),
        reply(review()),
    ]
    result = await rig.run()
    assert len(rig.calls) == 4 and result["content"] is not None
    assert (
        rig.checkpoints[0]["content"] is None
        and rig.checkpoints[0]["signal"] == signal
    )
    assert rig.checkpoints[-1]["content"] == story()


@pytest.mark.parametrize("mode", ["brief", "deep"])
async def test_empty_writer_without_verifiable_prior_does_not_spend_a_review_call(
    rig, mode
):
    rig.replies = [reply(writer())]
    result = await rig.run(mode=mode)
    assert len(rig.calls) == 1 and result["reason"] == "withheld"
    assert (
        result["assessments"] == []
        and result["issues"][0]["reason"] == "empty_component_review_skipped"
    )
    assert not rig.checkpoints


async def test_invalid_writer_output_is_not_mislabeled_as_provider_outage(rig):
    rig.replies = [reply({"content": None})]
    result = await rig.run(mode="deep")
    assert result["reason"] == "invalid_output"
    assert result["issues"][0]["reason"] == "writer:writer_envelope_invalid"


async def test_invalid_review_output_records_review_phase_without_publishing_prose(
    rig,
):
    rig.replies = [
        reply(writer(story())),
        reply({"prose": "I approve everything"}),
    ]
    result = await rig.run()
    assert result["reason"] == "invalid_output" and result["content"] is None
    assert result["issues"][0]["reason"].startswith("review:")


async def test_meaningful_same_source_chart_can_be_prepared_and_approved_in_brief(
    rig,
):
    content = story(chart=True)
    content["chart"]["points"][1]["decimal_value"] = "-2"
    rig.replies = [reply(writer(content)), reply(review(chart="approved"))]
    result = await rig.run(mode="brief")
    assert (
        result["content"]["chart"] == content["chart"] and len(rig.calls) == 2
    )
    rules = rig.calls[0]["prompt"]["output_rules"]
    assert "brief和deep都要检查" in rules and "2–6个同口径数据点" in rules
    assert "需要看清什么差异、用什么参照、理解后意味着什么" in rules
    assert "只有数值图确实比文字更能解释这个问题" in rules
    assert "作者自设门槛、运行次数不自动具有图表价值" in rules
    assert "缺少解释价值就chart=null" in rules
    assert "若有就在本轮给chart" not in rules
    assert "不能把同比与环比" in rules and "没有合适数据就null" in rules
    validate_result(result)


@pytest.mark.parametrize("mode", ["brief", "deep"])
async def test_standalone_chart_guidance_reaches_author_and_independent_chart_review(
    rig, mode
):
    """Prompt plumbing only; a simulated approval does not prove chart clarity."""
    content = story(chart=True)
    content["chart"]["unit"] = "Cohen's d（离线虚构比较）"
    rig.replies = [reply(writer(content)), reply(review(chart="approved"))]
    result = await rig.run(mode=mode, policy=reader_policy())
    author, reviewer = rig.calls
    assert author["prompt"]["chart_guidance"] == _CHART_GUIDANCE
    assert "独立图题" in _CHART_GUIDANCE
    assert "模型名、组名不能替代背景" in _CHART_GUIDANCE
    assert "比较基线是谁必须在图内说清" in _CHART_GUIDANCE
    assert "数据或实验时期" in _CHART_GUIDANCE
    assert "caption先说一个主要洞见" in _CHART_GUIDANCE
    assert "零点及方向，不把它当百分比" in _CHART_GUIDANCE
    assert "不自行加入“大/中/小效果”等统计阈值" in _CHART_GUIDANCE
    assert "图片看不到时仍有意义" in _CHART_GUIDANCE
    assert "limitations只留影响这张图结论的关键边界" in _CHART_GUIDANCE
    assert "已有材料不足以支持自足比较就chart=null" in _CHART_GUIDANCE
    review_rules = reviewer["prompt"]["chart_review_rules"]
    assert review_rules.startswith(_CHART_GUIDANCE)
    assert (
        "先遮住正文" in review_rules
        and "不能只核对数字与来源相等" in review_rules
    )
    assert "只将chart标blocked" in review_rules
    assert "单纯措辞偏好留findings" in review_rules
    assert "图卡应脱离正文自足" in author["instructions"]
    # Statistical labels are not lexical vetoes: source-backed review decides.
    assert result["content"] == content and len(rig.calls) == 2
    validate_result(result)


async def test_ambiguous_chart_review_discards_only_chart_without_another_model_round(
    rig,
):
    """Reproduce the opaque-title shape, with an explicitly simulated review finding."""
    content = story(chart=True)
    content["chart"].update(
        question="哪一层情境意识改善最大",
        metric="Cohen's d",
        unit="Cohen's d",
        caption="离线虚构说明，仅描述哪根柱最高。",
    )
    issue = {
        "component": "chart",
        "claim": content["chart"]["question"],
        "reason": "离线模拟：图中缺少对象、比较基线及尺度方向，正文不能替图补全。",
        "evidence": ["packet/source"],
        "action": "remove",
    }
    rig.replies = [
        reply(writer(content)),
        reply(review(chart="blocked", issues=[issue])),
    ]
    result = await rig.run()
    assert result["content"] == body_content(content) and len(rig.calls) == 2
    assert result["reason"] == "approved"
    assert result["issues"][0]["component"] == "chart"
    assert result["issues"][0]["reason"] == issue["reason"]
    validate_result(result)


async def test_absent_chart_adds_no_chart_review_instruction_or_extra_model_round(
    rig,
):
    rig.replies = [reply(writer(story())), reply(review())]
    result = await rig.run()
    assert result["content"] == story() and len(rig.calls) == 2
    assert "chart_review_rules" not in rig.calls[1]["prompt"]
    assert next(a for a in result["assessments"] if a["component"] == "chart")[
        "status"
    ] == ("not_present")
    validate_result(result)


def reader_policy():
    directory = Path(__file__).resolve().parents[1] / "src/newsletter/policy"
    return {
        "editorial.md": (directory / "story-editorial.md").read_text(
            encoding="utf-8"
        ),
        "reader-profile.md": (directory / "reader-profile.md").read_text(
            encoding="utf-8"
        ),
    }


@pytest.mark.parametrize(
    "mode,kind",
    [
        ("brief", "ai_ml"),
        ("deep", "ai_ml"),
        ("brief", "economy"),
        ("deep", "world"),
    ],
)
async def test_reader_first_guidance_reaches_writer_without_new_review_gate(
    rig, mode, kind
):
    """Offline prompt plumbing, not evidence that an LLM writes better prose."""
    content = {**story(), "kind": kind}
    policy = reader_policy()
    rig.replies = [reply(writer(content)), reply(review())]
    result = await rig.run(mode=mode, policy=policy)
    assert result["content"] == content and len(rig.calls) == 2
    author, reviewer = rig.calls
    assert author["prompt"]["writing_guidance"] == _WRITING_GUIDANCE
    assert author["prompt"]["reader_profile"] == policy["reader-profile.md"]
    assert all(
        call["instructions"] == policy["editorial.md"] for call in rig.calls
    )
    assert "先交代背景、要解决的问题和原来怎么做" in _WRITING_GUIDANCE
    assert "世界新闻和经济报道" in _WRITING_GUIDANCE
    assert "术语或缩写首次出现" in _WRITING_GUIDANCE
    assert "只保留能帮助理解变化的少量数字" in _WRITING_GUIDANCE
    assert "而不是扩写摘要、增加数字、术语或段数" in _WRITING_GUIDANCE
    assert "不要把搜索/open、JSON、审校/修订经过倒进报道" in _WRITING_GUIDANCE
    assert "不是新增字数、术语或背景的审校阻断条件" in _WRITING_GUIDANCE
    assert "writing_guidance" not in reviewer["prompt"]
    assert "不因为文风或可有可无扩展研究阻断" in reviewer["prompt"]["rules"]
    paragraphs = author["schema"]["properties"]["content"]["anyOf"][0][
        "properties"
    ]["paragraphs"]
    assert paragraphs["minItems"] == 1
    assert paragraphs["maxItems"] == (2 if mode == "brief" else 16)
    validate_result(result)


@pytest.mark.parametrize("known", [True, False])
async def test_source_identity_and_contribution_remain_untrusted_writer_context(
    rig, known
):
    """New candidate fields propagate without becoming citations or approval."""
    details = {
        "authors": "Fixture Author",
        "affiliations": "Fixture Research Institute",
        "venue": "Fixture Conference",
        "publication_status": "Fixture preprint, not an acceptance claim",
        "contribution": "A different way to examine a fictional bottleneck",
        "source_basis": "Fixture discovery lead; not a quality judgement",
    }
    candidate = {
        "id": "candidate-a",
        **{name: value if known else "" for name, value in details.items()},
        "evidence_urls": [URL] if known else [],
    }
    original = deepcopy(candidate)
    rig.replies = [reply(writer(story())), reply(review())]
    result = await rig.run(candidates=[candidate])
    prompt = rig.calls[0]["prompt"]
    assert (
        prompt["candidates_untrusted"] == [original] and candidate == original
    )
    assert prompt["available_citations"] == [
        "packet/source",
        "packet/publication",
    ]
    assert "只是待核线索，不是发表引用或质量背书" in prompt["writing_guidance"]
    assert "不得把网页发布方当作者单位" in prompt["writing_guidance"]
    assert len(rig.calls) == 2
    validate_result(result)


async def test_local_repair_preserves_reader_guidance_and_independently_approved_signal(
    rig,
):
    """The existing four-call repair path remains bounded and separately reviewed."""
    original, fixed = story(), story("修正后的虚构事件，不是真实报道。")
    signal = story("仅确认虚构事件存在。")
    policy = reader_policy()
    rig.replies = [
        reply(writer(original, signal)),
        reply(review(body="blocked", signal="approved")),
        reply(writer(fixed)),
        reply(review()),
    ]
    result = await rig.run(policy=policy)
    assert result["content"] == fixed and result["signal"] == signal
    assert len(rig.calls) == 4 and len(rig.checkpoints) == 2
    assert (
        rig.checkpoints[0]["content"] is None
        and rig.checkpoints[0]["signal"] == signal
    )
    for index in (0, 2):
        prompt = rig.calls[index]["prompt"]
        assert prompt["writing_guidance"] == _WRITING_GUIDANCE
        assert prompt["chart_guidance"] == _CHART_GUIDANCE
        assert prompt["reader_profile"] == policy["reader-profile.md"]
    assert "repair只在原修订范围内改善解释" in _WRITING_GUIDANCE
    assert "不得更改已批准的简讯" in rig.calls[2]["prompt"]["task"]
    assert len({call["path"] for call in rig.calls}) == 4
    for checkpoint in rig.checkpoints:
        validate_result(checkpoint)


async def test_reader_guidance_adds_no_length_or_background_gate_for_abstract_brief(
    rig,
):
    """A simulated reviewer decision is not changed by a new stylistic validator."""
    rig.packet["content"]["sources"][0]["access_scope"] = "abstract"
    rig.packet["content_hash"] = content_hash(rig.packet["content"])
    content = story("离线虚构事件。")
    rig.replies = [reply(writer(content)), reply(review())]
    result = await rig.run(policy=reader_policy())
    assert result["content"] == content and result["issues"] == []
    assert len(rig.calls) == 2
    validate_result(result)


@pytest.mark.parametrize("kind", ["ai_ml", "economy"])
async def test_explainer_examples_reach_writer_without_formula_or_statistic_keyword_gate(
    rig, kind
):
    """Check targeted guidance, not real quality; model-approved text is not censored."""
    content = {
        **story("离线虚构统计记录：参数λ、78.64%、样本期；不是实际研究结论。"),
        "kind": kind,
    }
    rig.replies = [reply(writer(content)), reply(review())]
    result = await rig.run(policy=reader_policy())
    guidance = rig.calls[0]["prompt"]["writing_guidance"]
    assert "帮助读者想明白的解释者" in guidance
    assert "定义术语只是起点" in guidance
    assert "本篇相对原有认识的增量" in guidance
    assert "把公式换成另一种数学写法也不等于解释了机制" in guidance
    assert "AI例：" in guidance and "金融例：" in guidance
    assert "只是表达对照，不是本题证据" in guidance
    assert "不编造真实应用或实验" in guidance
    assert "不以通俗为由抹去必要限制" in guidance
    assert result["content"] == content and result["issues"] == []
    assert len(rig.calls) == 2
    assert "writing_guidance" not in rig.calls[1]["prompt"]
    validate_result(result)
