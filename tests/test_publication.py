"""Offline publication admission, stable checkpoints and next-day topic memory."""

from copy import deepcopy

import pytest
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.contracts import content_hash, parse_message, validate_draft
from newsletter.rendering import render_edition
from newsletter.store import Store, StoreError
from newsletter.workflow.publication import (
    MAX_VERSIONS,
    PublicationError,
    PublicationRepository,
    assemble,
    body_content,
    validate_result,
)

DAY = "2026-09-06"
NEXT_DAY = "2026-09-07"
URL = "https://example.org/research"


def task(number=1, **changes):
    return {
        "id": f"story-{number}",
        "candidate_ids": [f"candidate-{number}"],
        "question": f"Synthetic research question {number}",
        "why": "A concrete new result merits investigation.",
        "priority": number,
        "evidence_context": "Read the actual study and its controlled comparison.",
        "source_urls": [URL],
        **changes,
    }


def packet(number=1):
    content = {
        "title": "Synthetic material",
        "body": "Only a test fixture, never material for a real newsletter.",
        "sources": [
            {
                "id": "original",
                "title": "Synthetic original source",
                "url": f"{URL}/{number}",
                "published_at": DAY,
                "access_scope": "full_text",
                "excerpt": "A controlled comparison was reported.",
            }
        ],
        "tags": ["test-fixture"],
    }
    return {
        "id": f"packet-{number}",
        "workflow_id": "test-publication",
        "producer_id": "test",
        "content": content,
        "content_hash": content_hash(content),
        "created_at": DAY + "T08:00:00Z",
        "is_fixture": True,
    }


def story(number=1, **changes):
    return {
        "story_id": f"story-{number}",
        "title": f"Synthetic verified topic {number}",
        "kind": "feature",
        "paragraphs": [
            {
                "text": f"Synthetic result {number} with its boundary intact.",
                "citations": [f"packet-{number}/original"],
            }
        ],
        "limitations": "Synthetic limitation must remain beside its claim.",
        **changes,
    }


def receipt(component, value, packets, **changes):
    return {
        "round": "initial",
        "component": component,
        "status": "approved",
        "content_hash": content_hash(value),
        "findings": ["Synthetic independent review passed."],
        "searched": True,
        "opened": True,
        "opened_urls": [source["url"] for p in packets for source in p["content"]["sources"]],
        "writer_job_id": "writer-job",
        "reviewer_job_id": "independent-reviewer-job",
        **changes,
    }


def result(number=1, mode="brief", *, content=True, signal=False, **changes):
    packets = [packet(number)]
    value = story(number) if content is True else content if content else None
    confirmed = story(number, title="Confirmed event, uncertain significance") if signal else None
    assessments = []
    if value:
        assessments.append(receipt("body", body_content(value), packets))
        for field, component in (("recommended_reading", "reading"), ("chart", "chart")):
            if field in value:
                assessments.append(receipt(component, value[field], packets))
    if confirmed:
        assessments.append(receipt("signal", confirmed, packets))
    return {
        "story_id": f"story-{number}",
        "mode": mode,
        "content": value,
        "signal": confirmed,
        "packets": packets,
        "assessments": assessments,
        "issues": [],
        "reason": "Synthetic approved checkpoint" if value or confirmed else "unavailable",
        "provenance": {"packets_hash": content_hash(packets)},
        **changes,
    }


def withdrawal_result(prior=None, *, signal=False, content=False):
    prior = prior or result(signal=True)
    value = result(mode="deep", content=content)
    reviewed = receipt(
        "body",
        body_content(prior["content"]),
        value["packets"],
        status="blocked",
        writer_job_id="deep-writer",
        reviewer_job_id="deep-reviewer",
    )
    if content:
        value["assessments"][0]["reviewer_job_id"] = "deep-reviewer"
    else:
        value["assessments"].append(reviewed)
    value["withdrawals"] = [
        {
            "story_id": prior["story_id"],
            "mode": "brief",
            "content_hash": content_hash(body_content(prior["content"])),
            "affected_signal_hash": content_hash(prior["signal"]) if signal else "",
            "claim": prior["content"]["paragraphs"][0]["text"],
            "reason": "A fresh independent source check establishes a concrete factual error.",
            "evidence": ["packet-1/original"],
            "searched": True,
            "opened": True,
            "opened_urls": [URL + "/1"],
            "writer_job_id": "writer-job",
            "reviewer_job_id": "deep-reviewer",
        }
    ]
    return value


def delivery_receipt(repository, run_id, built, state="simulated"):
    store = repository.store
    store.save_workflow_supplements(run_id, built["packets"])
    ids = [packet["id"] for packet in built["packets"]]
    issue = store.prepare(
        {"request_key": run_id, "issue_date": DAY, "packet_ids": ids},
        workflow_binding={
            "run_id": run_id,
            "result": {"draft": built["draft"], "review": built["review"]},
            "required_packets": ids,
            "projection_required": False,
        },
    )
    rendered = render_edition(built["draft"], built["packets"], DAY, is_fixture=True)
    store.finish(
        issue["id"], state="ready", draft=built["draft"], review=built["review"], rendered=rendered
    )
    if state != "not_requested":
        store.reserve_send(
            {
                "id": issue["id"],
                "request_key": "send-" + run_id,
                "expected_render_hash": rendered["render_hash"],
            }
        )
        store.finish(issue["id"], delivery_state=state)
    return issue


@pytest.fixture
def repository(tmp_path):
    store = Store(tmp_path / "newsletter.sqlite3", "mock")
    yield PublicationRepository(store)
    store.close()


def test_approved_story_and_summary_use_public_proto():
    value = result()
    validate_result(value)
    parse_message(value["content"], pb.StoryContent)
    built = assemble("run-1", DAY, [task()], [value])
    parse_message(built["coverage"], pb.PublicationSummary)
    validate_draft(built["draft"], built["packets"])
    assert built["review"]["passed"] is True
    assert built["notion_required"] is False
    assert built["draft"]["sections"][0]["paragraphs"][0]["text"] == (
        value["content"]["title"] + "\n" + value["content"]["paragraphs"][0]["text"]
    )
    assert value == result()  # Assembly cannot mutate an approved source object.


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.update(assessments=[]),
        lambda r: r["content"].update(title="Unreviewed replacement title"),
        lambda r: r["content"].update(limitations="Changed limitation"),
        lambda r: r["content"]["paragraphs"][0].update(text="New unreviewed claim"),
        lambda r: r["content"].update(story_id="other-story"),
        lambda r: r["assessments"][0].update(status="blocked"),
        lambda r: r["assessments"][0].update(searched=False),
        lambda r: r["assessments"][0].update(opened=False),
        lambda r: r["assessments"][0].update(opened_urls=[]),
        lambda r: r["assessments"][0].update(opened_urls=["https://example.org/other"]),
        lambda r: r["assessments"][0].update(writer_job_id="independent-reviewer-job"),
        lambda r: r["assessments"][0].update(reviewer_job_id=""),
        lambda r: r["assessments"][0].update(round="manually-approved"),
        lambda r: r["packets"][0]["content"]["sources"][0].update(
            url="https://example.org/changed"
        ),
        lambda r: r.update(provenance={"packets_hash": "0" * 64}),
        lambda r: r.update(extra_field="not part of the internal contract"),
    ],
)
def test_naked_passes_and_mutated_content_evidence_or_review_do_not_admit_text(edit):
    value = result()
    edit(value)
    with pytest.raises(PublicationError):
        validate_result(value)


def test_same_round_unresolved_issue_cannot_coexist_with_component_approval():
    value = result(
        issues=[
            {
                "round": "initial",
                "component": "body",
                "claim": "Synthetic result 1",
                "reason": "The number is incorrect",
                "evidence": ["packet-1/original"],
                "action": "correct",
            }
        ]
    )
    with pytest.raises(PublicationError):
        validate_result(value)
    value["assessments"][0]["round"] = "repair"
    validate_result(value)


def test_receipt_does_not_certify_unknown_citation_or_metadata_as_read_evidence():
    for ref, scope in (("unknown/source", "full_text"), ("packet-1/original", "metadata")):
        value = result()
        value["content"]["paragraphs"][0]["citations"] = [ref]
        value["packets"][0]["content"]["sources"][0]["access_scope"] = scope
        value["assessments"][0] = receipt("body", value["content"], value["packets"])
        value["provenance"]["packets_hash"] = content_hash(value["packets"])
        with pytest.raises(PublicationError):
            validate_result(value)


def test_unapproved_extra_never_sneaks_into_approved_body():
    value = result()
    value["content"]["recommended_reading"] = {
        "citation": "packet-1/original",
        "reason": "A new unreviewed claim attached to an approved body.",
        "supporting_citations": [],
    }
    with pytest.raises(PublicationError):
        validate_result(value)
    value["content"].pop("recommended_reading")
    validate_result(value)


def test_multiple_reading_sources_all_need_independent_open_receipt():
    value = result()
    value["packets"].append(packet(2))
    reading = {
        "citation": "packet-1/original",
        "reason": "One primary reading link, with an additional fact supported separately.",
        "supporting_citations": ["packet-2/original"],
    }
    value["content"]["recommended_reading"] = reading
    value["assessments"].append(receipt("reading", reading, value["packets"]))
    value["provenance"]["packets_hash"] = content_hash(value["packets"])
    validate_result(value)
    built = assemble("run-1", DAY, [task()], [value])
    assert len(built["packets"]) == 2
    value["assessments"][-1]["opened_urls"] = [URL + "/1"]
    with pytest.raises(PublicationError):
        validate_result(value)


def test_each_topic_has_disposition_and_another_story_failure_does_not_block_issue():
    tasks = [task(i) for i in range(1, 6)]
    values = [
        result(1),
        result(1, "deep"),
        result(2),
        result(2, "deep", content=False),
        result(3, content=False, signal=True),
        result(4, content=False),
        result(5, assessments=[]),
    ]
    built = assemble("run-1", DAY, tasks, values, reason="deadline")
    assert [s["disposition"] for s in built["coverage"]["stories"]] == [
        "deep",
        "brief",
        "watch",
        "deferred",
        "deferred",
    ]
    assert [s["story_id"] for s in built["coverage"]["stories"]] == [t["id"] for t in tasks]
    assert built["coverage"]["mode"] == "partial"
    assert built["coverage"]["reason"] == "deadline"
    assert len(built["draft"]["sections"]) == 3
    assert [s["kind"] for s in built["draft"]["sections"]] == ["world", "feature", "context"]
    assert {p["id"] for p in built["packets"]} == {"packet-1", "packet-2", "packet-3"}
    assert "Synthetic research question 4" not in str(built["draft"])
    assert "2 个入选选题暂未刊出" in built["draft"]["introduction"]
    assert "Synthetic research question 4" not in built["draft"]["introduction"]


def test_deadline_disclosure_does_not_call_approved_deep_a_brief_or_complete_issue():
    built = assemble("run-1", DAY, [task()], [result(mode="deep")], reason="deadline")
    assert built["coverage"]["mode"] == "partial"
    assert "已完成独立核验" in built["draft"]["introduction"]
    assert "简讯" not in built["draft"]["introduction"]
    assert built["coverage"]["stories"][0]["disposition"] == "deep"


def test_only_two_priority_deeps_and_other_complete_briefs_are_preserved():
    tasks = [task(3), task(2), task(1), task(4)]
    values = [result(i, mode) for i in range(1, 5) for mode in ("brief", "deep")]
    built = assemble("run-1", DAY, tasks, values)
    assert [s["story_id"] for s in built["coverage"]["stories"]] == [
        "story-1",
        "story-2",
        "story-3",
        "story-4",
    ]
    assert [s["disposition"] for s in built["coverage"]["stories"]] == [
        "deep",
        "deep",
        "brief",
        "brief",
    ]
    assert len(built["draft"]["sections"]) == 3
    assert built["draft"]["sections"][1]["paragraphs"] == values[1]["content"]["paragraphs"]


def test_later_failure_or_corrupt_result_does_not_replace_earlier_approved_checkpoint():
    initial = result(content=False, signal=True)
    good = result()
    failed = result(content=False, reason="provider_timeout")
    corrupted = result(content=story(title="Unreviewed new text"), assessments=[])
    for values, disposition in (([initial, failed], "watch"), ([good, failed, corrupted], "brief")):
        built = assemble("run-1", DAY, [task()], values)
        assert built["coverage"]["stories"][0]["disposition"] == disposition
        assert "Unreviewed new text" not in str(built["draft"])


def test_explicit_independent_exact_body_withdrawal_keeps_unaffected_confirmed_signal():
    prior = result(signal=True)
    correction = withdrawal_result(prior)
    validate_result(correction)
    built = assemble("run-1", DAY, [task(), task(2)], [prior, correction, result(2)])
    assert [s["disposition"] for s in built["coverage"]["stories"]] == ["watch", "brief"]
    assert "Confirmed event, uncertain significance" in str(built["draft"])
    assert "Synthetic verified topic 1" not in str(built["draft"])


def test_signal_is_removed_only_when_its_exact_hash_is_explicitly_affected():
    prior = result(signal=True)
    correction = withdrawal_result(prior, signal=True)
    built = assemble("run-1", DAY, [task(), task(2)], [prior, correction, result(2)])
    assert [s["disposition"] for s in built["coverage"]["stories"]] == ["deferred", "brief"]
    assert "明确事实错误" in built["coverage"]["stories"][0]["reason"]
    assert "Confirmed event" not in str(built["draft"])


def test_approved_corrected_deep_survives_withdrawal_of_an_old_brief():
    prior = result(signal=True)
    corrected = story(
        paragraphs=[
            {
                "text": "A new independently verified correction; the exact old body is withdrawn.",
                "citations": ["packet-1/original"],
            }
        ]
    )
    correction = withdrawal_result(prior, signal=True, content=corrected)
    built = assemble("run-1", DAY, [task()], [prior, correction])
    assert built["coverage"]["stories"][0]["disposition"] == "deep"
    assert "A new independently verified correction" in str(built["draft"])


@pytest.mark.parametrize(
    "change",
    [
        {"content_hash": "0" * 64},
        {"claim": "A different long claim not present in the old body."},
        {"writer_job_id": "not-the-original-author"},
        {"affected_signal_hash": "0" * 64},
    ],
)
def test_withdrawal_cannot_target_unknown_body_signal_author_or_unquoted_claim(change):
    prior = result(signal=True)
    correction = withdrawal_result(prior)
    correction["withdrawals"][0].update(change)
    built = assemble("run-1", DAY, [task()], [prior, correction])
    assert built["coverage"]["stories"][0]["disposition"] == "brief"


@pytest.mark.parametrize(
    "change",
    [
        {"searched": False},
        {"opened": False},
        {"opened_urls": []},
        {"evidence": []},
        {"evidence": ["unknown/source"]},
        {"claim": "too short"},
        {"reason": ""},
        {"reviewer_job_id": "writer-job"},
        {"reviewer_job_id": "unobserved-review"},
        {"story_id": "another-story"},
        {"mode": "deep"},
    ],
)
def test_generic_deep_failure_or_unverified_withdrawal_cannot_retract_good_brief(change):
    prior = result(signal=True)
    correction = withdrawal_result(prior)
    correction["withdrawals"][0].update(change)
    with pytest.raises(PublicationError):
        validate_result(correction)
    built = assemble("run-1", DAY, [task()], [prior, correction])
    assert built["coverage"]["stories"][0]["disposition"] == "brief"


def test_withdrawal_works_across_checkpoint_replay_and_next_deep_prior(repository):
    prior = result(signal=True)
    correction = withdrawal_result(prior)
    repository.save("run-1", task(), "brief", prior, issue_date=DAY)
    repository.save("run-1", task(), "deep", correction, issue_date=DAY)
    prior_view = repository.best_result("run-1", "story-1")
    assert prior_view["content"] is None
    assert prior_view["signal"] == prior["signal"]
    validate_result(prior_view)
    assert repository.results("run-1")[0] == prior  # Immutable audit version remains intact.
    both = withdrawal_result(prior, signal=True)
    repository.save("run-1", task(), "deep", both, issue_date=DAY)
    assert repository.best_result("run-1", "story-1") is None


def test_latest_approved_complete_version_is_chosen_without_paragraph_splicing():
    initial = result()
    revised = result(
        content=story(
            paragraphs=[
                {
                    "text": "A complete independently reviewed replacement, with all boundaries.",
                    "citations": ["packet-1/original"],
                }
            ]
        )
    )
    revised["assessments"][0]["round"] = "repair"
    built = assemble("run-1", DAY, [task()], [initial, revised])
    text = str(built["draft"])
    assert "complete independently reviewed replacement" in text
    assert "Synthetic result 1" not in text


def test_capacity_marks_whole_topic_deferred_instead_of_cutting_approved_paragraphs():
    tasks = [task(i) for i in range(1, 19)]
    built = assemble("run-1", DAY, tasks, [result(i) for i in range(1, 19)])
    coverage = built["coverage"]["stories"]
    assert len(coverage) == 18
    assert [s["disposition"] for s in coverage[:16]] == ["brief"] * 16
    assert [s["disposition"] for s in coverage[16:]] == ["deferred"] * 2
    assert all("容量" in s["reason"] for s in coverage[16:])


def test_no_approved_public_content_is_explicit_error_not_empty_success():
    for values in ([], [result(content=False)], [result(assessments=[])]):
        with pytest.raises(PublicationError) as caught:
            assemble("run-1", DAY, [task()], values)
        assert caught.value.code == "no_publishable_content"
    with pytest.raises(PublicationError) as caught:
        assemble("run-1", DAY, [], [])
    assert caught.value.code == "no_publishable_content"


def test_no_findings_plan_is_a_valid_honest_record_not_a_successful_empty_issue(repository):
    assert repository.save_plan("run-1", DAY, []) == []
    assert repository.plan("run-1") == []
    assert repository.pending_history(NEXT_DAY) == []


def test_immutable_checkpoint_replay_returns_detached_data_and_preserves_all_versions(repository):
    t = task()
    initial, final = result(content=False, signal=True), result()
    repository.save_plan("run-1", DAY, [t])
    saved = repository.save("run-1", t, "brief", initial, issue_date=DAY)
    saved["reason"] = "caller cannot mutate stored checkpoint"
    repository.save("run-1", t, "brief", final, issue_date=DAY)
    repository.save("run-1", t, "brief", final, issue_date=DAY)
    assert repository.results("run-1") == [initial, final]
    assert repository.results("other-run") == []
    with pytest.raises(StoreError):
        repository.save("run-1", task(priority=2), "deep", result(mode="deep"), issue_date=DAY)
    with pytest.raises(StoreError):
        repository.save("run-1", t, "deep", result(mode="deep"), issue_date=NEXT_DAY)


def test_checkpoint_versions_and_per_run_story_count_are_bounded(repository):
    for i in range(MAX_VERSIONS):
        repository.save("run-1", task(), "brief", result(reason=f"checkpoint-{i}"), issue_date=DAY)
    with pytest.raises(PublicationError) as caught:
        repository.save("run-1", task(), "brief", result(reason="overflow"), issue_date=DAY)
    assert caught.value.code == "publication_capacity"
    with pytest.raises(PublicationError):
        repository.save_plan("run-2", DAY, [task(i) for i in range(1, 101)])


def test_plan_replay_frozen_identity_and_unknown_task_refused(repository):
    plan = [task(), task(2)]
    assert repository.save_plan("run-1", DAY, plan) == plan
    assert repository.save_plan("run-1", DAY, deepcopy(plan)) == plan
    for date, tasks in ((NEXT_DAY, plan), (DAY, [task(2), task()]), (DAY, [task()])):
        with pytest.raises(StoreError):
            repository.save_plan("run-1", date, tasks)
    with pytest.raises(StoreError):
        repository.save("run-1", task(3), "brief", result(3), issue_date=DAY)
    assert repository.plan("run-1") == plan
    assert repository.plan("unknown") == []
    returned = repository.plan("run-1")
    returned[0]["question"] = "Not allowed to mutate the persisted task"
    assert repository.plan("run-1") == plan


def test_best_result_for_deep_prior_never_returns_last_failed_over_approved_brief(repository):
    initial = result(content=False, signal=True)
    brief = result()
    failed = result(content=False)
    repository.save("run-1", task(), "brief", initial, issue_date=DAY)
    assert repository.best_result("run-1", "story-1") == initial
    repository.save("run-1", task(), "brief", brief, issue_date=DAY)
    repository.save("run-1", task(), "brief", failed, issue_date=DAY)
    assert repository.best_result("run-1", "story-1") == brief
    assert repository.best_result("run-1", "story-1", "deep") is None
    assert repository.best_result("run-1", "unselected") is None
    with pytest.raises(PublicationError):
        repository.best_result("run-1", "story-1", "unknown")


@pytest.mark.parametrize(
    "change",
    [
        {"id": "bad/id"},
        {"priority": True},
        {"priority": 0},
        {"candidate_ids": ["a", "a"]},
        {"candidate_ids": [{}]},
        {"question": ""},
        {"source_urls": ["http://127.0.0.1/private"]},
    ],
)
def test_invalid_plan_boundaries_have_finite_publication_errors(repository, change):
    with pytest.raises(PublicationError):
        repository.save_plan("run-1", DAY, [task(**change)])
    with pytest.raises(PublicationError):
        assemble("run-1", DAY, [task(**change)], [])


def test_frozen_publication_is_reconstructed_from_ledger_and_not_mutated_by_late_deep(repository):
    tasks, values = [task(), task(2)], [result()]
    repository.save_plan("run-1", DAY, tasks)
    repository.save("run-1", tasks[0], "brief", values[0], issue_date=DAY)
    built = assemble("run-1", DAY, tasks, repository.results("run-1"), reason="deadline")
    frozen = repository.record_publication("run-1", DAY, tasks, built)
    assert frozen == built == repository.get_publication("run-1")
    assert repository.record_publication("run-1", DAY, tasks, built) == built
    repository.save("run-1", tasks[0], "brief", values[0], issue_date=DAY)
    with pytest.raises(StoreError):
        repository.save("run-1", tasks[0], "deep", result(mode="deep"), issue_date=DAY)
    with pytest.raises(StoreError):
        repository.save("run-1", tasks[1], "brief", result(2), issue_date=DAY)
    frozen["draft"]["title"] = "Mutated caller object"
    assert repository.get_publication("run-1")["draft"]["title"] == "每日简报"


def test_fake_pass_or_unrecorded_approved_text_cannot_be_frozen(repository):
    repository.save_plan("run-1", DAY, [task()])
    built = assemble("run-1", DAY, [task()], [result()])
    with pytest.raises(PublicationError):
        repository.record_publication("run-1", DAY, [task()], built)
    repository.save("run-1", task(), "brief", result(), issue_date=DAY)
    for key, replacement in (("title", "Unreviewed headline"), ("limitations", "Unreviewed fact")):
        bad = deepcopy(built)
        bad["draft"][key] = replacement
        with pytest.raises(PublicationError) as caught:
            repository.record_publication("run-1", DAY, [task()], bad)
        assert caught.value.code == "invalid_publication_snapshot"
    assert repository.get_publication("run-1") is None


@pytest.mark.parametrize("feature_cap", [0, 1, 2])
def test_freeze_reconstruction_preserves_admission_order_at_feature_and_paragraph_capacity(
    repository, feature_cap
):
    tasks = [task(i) for i in range(1, 19)]
    repository.save_plan("run-1", DAY, tasks)
    for selected in tasks:
        number = selected["priority"]
        repository.save("run-1", selected, "brief", result(number), issue_date=DAY)
        if number in (1, 2, 18):
            repository.save("run-1", selected, "deep", result(number, "deep"), issue_date=DAY)
    values = repository.results("run-1")
    built = assemble("run-1", DAY, tasks, values, max_features=feature_cap)
    assert sum(s["disposition"] == "deep" for s in built["coverage"]["stories"]) == feature_cap
    assert repository.record_publication("run-1", DAY, tasks, built) == built


def test_failed_before_any_review_still_has_next_day_selected_topic_memory(repository):
    repository.save_plan("run-1", DAY, [task(), task(2)])
    assert repository.pending_history(DAY) == []
    pending = repository.pending_history(NEXT_DAY)
    assert [p["story_id"] for p in pending] == ["story-1", "story-2"]
    assert all(p["disposition"] == "deferred" for p in pending)
    assert pending[0]["evidence_context"] == task()["evidence_context"]
    assert pending[0]["source_urls"] == [URL]
    assert "不是证据" in pending[0]["reason"]


def test_published_deep_closes_old_followup_even_if_task_identifier_changes(repository):
    repository.save_plan("run-old", "2026-09-05", [task()])
    renamed = task(2, candidate_ids=["candidate-1"])
    approved = result(2, "deep")
    repository.save_plan("run-new", DAY, [renamed])
    repository.save("run-new", renamed, "deep", approved, issue_date=DAY)
    built = assemble("run-new", DAY, [renamed], [approved])
    repository.record_publication("run-new", DAY, [renamed], built)
    assert repository.pending_history(NEXT_DAY)[0]["disposition"] == "deferred"
    delivery_receipt(repository, "run-new", built)
    assert repository.pending_history(NEXT_DAY) == []


def test_brief_watch_and_deferred_priorities_survive_next_day_history(repository):
    tasks = [task(3), task(1), task(2), task(4)]
    values = [result(), result(2, content=False, signal=True), result(3, "deep")]
    repository.save_plan("run-1", DAY, tasks)
    for value in values:
        selected = next(t for t in tasks if t["id"] == value["story_id"])
        repository.save("run-1", selected, value["mode"], value, issue_date=DAY)
    built = assemble("run-1", DAY, tasks, values)
    repository.record_publication("run-1", DAY, tasks, built)
    delivery_receipt(repository, "run-1", built)
    assert [p["disposition"] for p in repository.pending_history(NEXT_DAY)] == [
        "brief",
        "watch",
        "deferred",
    ]
    assert [p["priority"] for p in repository.pending_history(NEXT_DAY, limit=2)] == [1, 2]


@pytest.mark.parametrize(
    "state",
    ["not_requested", "unknown", "submitting", "rejected", "simulated", "provider_accepted"],
)
def test_deep_topic_memory_closes_only_after_a_confirmed_send_receipt(repository, state):
    value = result(mode="deep")
    repository.save("run-1", task(), "deep", value, issue_date=DAY)
    built = assemble("run-1", DAY, [task()], [value])
    repository.record_publication("run-1", DAY, [task()], built)
    delivery_receipt(repository, "run-1", built, state)
    before = repository.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0]
    pending = repository.pending_history(NEXT_DAY)
    assert repository.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == before
    if state in {"simulated", "provider_accepted"}:
        assert pending == []
    else:
        assert len(pending) == 1
        assert pending[0]["disposition"] == "deferred"
        assert "勿自动重发原稿" in pending[0]["reason"]
