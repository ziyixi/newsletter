"""Durable publication boundaries with synthetic SQLite data only; never send mail."""

import copy
import sqlite3

import pytest
from test_usage import notification, record_one

from newsletter.collection.collector import MockCollector
from newsletter.collection.repository import RunRepository
from newsletter.editor import CodexEditor
from newsletter.store import Store, StoreError
from newsletter.workflow.pipeline import DagPipeline
from newsletter.workflow.state import WorkflowState


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "state.sqlite3", "mock")
    try:
        yield value
    finally:
        value.close()


def packet(store, key):
    return store.put_packet(
        {
            "request_key": key,
            "workflow_id": "synthetic",
            "content": {
                "title": "Synthetic " + key,
                "body": "Only an offline state-machine fixture, not news.",
                "sources": [
                    {
                        "id": "source",
                        "title": "Synthetic source",
                        "url": "https://example.org/fixture",
                        "excerpt": "Synthetic test only.",
                        "access_scope": "full_text",
                    }
                ],
                "tags": ["fixture"],
            },
        }
    )


def binding(run, packets):
    return {
        "run_id": run,
        "result": {
            "draft": {"title": "Synthetic draft"},
            "review": {"passed": True, "findings": []},
        },
        "required_packets": [item["id"] for item in packets],
    }


def request(key, packets):
    return {
        "request_key": key,
        "issue_date": "2026-09-06",
        "packet_ids": [p["id"] for p in packets],
    }


def ready(store, key, packets, required=None, run=None):
    edition = store.prepare(
        request(key, packets),
        workflow_binding=binding(run or key, packets if required is None else required),
    )
    # This tests the reservation boundary, not the already-covered model/renderer.
    return store.finish(
        edition["id"],
        state="ready",
        review={"passed": True, "findings": []},
        rendered={
            "html": "synthetic",
            "text": "synthetic",
            "chart_png": "",
            "render_hash": key + "-hash",
        },
    )


def approval(edition, key="send-fixture"):
    return {
        "id": edition["id"],
        "request_key": key,
        "expected_render_hash": edition["rendered"]["render_hash"],
    }


def test_usage_ledger_upserts_latest_cumulative_snapshot_not_each_notification(store):
    state = WorkflowState(store)
    sink = state.usage_sink("run-one")
    records = record_one()
    for row in records + [records[-1]]:
        sink(row)
    assert store.db.execute("SELECT COUNT(*) FROM model_usage").fetchone()[0] == 1
    assert state.usage("run-one")["usage"]["total_tokens"] == 120
    assert state.usage("run-one")["invocations"] == 1
    assert not state.usage("run-one")["partial"]
    assert state.usage("unrelated")["usage"] is None


def test_usage_scope_cannot_be_reassigned_after_recording(store):
    state = WorkflowState(store)
    row = record_one()[-1]
    state.usage_sink("original")(row)
    with pytest.raises(StoreError) as caught:
        state.usage_sink("other")(row)
    assert caught.value.code == "conflict"
    assert state.usage("original")["usage"]["total_tokens"] == 120
    assert state.usage("other")["usage"] is None


@pytest.mark.parametrize("snapshot", [0, 1, -1])
def test_usage_survives_restart_including_unknown_and_in_flight_snapshots(tmp_path, snapshot):
    path = tmp_path / "restart.sqlite3"
    before = Store(path, "mock")
    row = record_one()[snapshot]
    WorkflowState(before).usage_sink("run-one")(row)
    expected = WorkflowState(before).usage("run-one")
    before.close()
    after = Store(path, "mock")
    try:
        assert WorkflowState(after).usage("run-one") == expected
        assert expected["partial"] is (snapshot != -1)
        if snapshot == 0:
            assert expected["usage"] is None and expected["missing_invocations"] == 1
    finally:
        after.close()


def test_failed_attempts_and_successful_replacement_both_remain_in_usage(store):
    state = WorkflowState(store)
    failed = record_one()[-1]
    failed.update(status="failed", partial=True)
    succeeded = record_one(notification(200, 30))[-1]
    sink = state.usage_sink("one-run")
    sink(failed)
    sink(succeeded)
    summary = state.usage("one-run")
    assert summary["invocations"] == 2
    assert summary["usage"]["total_tokens"] == 350 and summary["partial"]


def test_prepare_writes_edition_and_frozen_workflow_binding_atomically(store):
    state = WorkflowState(store)
    source = packet(store, "adopted")
    bound = binding("run-one", [source])
    first = store.prepare(request("edition", [source]), workflow_binding=bound)
    assert state.edition(first["id"]) == {
        "run_id": "run-one",
        "result": bound["result"],
        "required_packets": [source["id"]],
    }
    assert (
        store.prepare(request("edition", [source]), workflow_binding=copy.deepcopy(bound)) == first
    )
    assert store.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 1


def test_binding_insert_failure_rolls_back_new_edition_and_queue_slot(store):
    state = WorkflowState(store)
    source = packet(store, "adopted")
    state.bind_edition("existing-binding", "occupied-run", {}, [source["id"]])
    with pytest.raises((sqlite3.IntegrityError, StoreError)):
        store.prepare(
            request("edition", [source]), workflow_binding=binding("occupied-run", [source])
        )
    assert store.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 0
    assert store.claim() is None
    assert store.prepare(
        request("edition", [source]), workflow_binding=binding("other-run", [source])
    )


@pytest.mark.parametrize("field", ["run_id", "result", "required_packets"])
def test_idempotent_prepare_cannot_change_frozen_workflow_binding(store, field):
    state = WorkflowState(store)
    source = packet(store, "adopted")
    original = binding("run-one", [source])
    first = store.prepare(request("edition", [source]), workflow_binding=original)
    changed = copy.deepcopy(original)
    changed[field] = {
        "run_id": "run-two",
        "result": {"draft": {"title": "changed"}},
        "required_packets": [],
    }[field]
    with pytest.raises(StoreError) as caught:
        store.prepare(request("edition", [source]), workflow_binding=changed)
    assert caught.value.code == "conflict"
    assert state.edition(first["id"])["result"] == original["result"]


def test_existing_unbound_edition_cannot_silently_ignore_new_workflow_binding(store):
    source = packet(store, "adopted")
    store.prepare(request("edition", [source]))
    with pytest.raises(StoreError) as caught:
        store.prepare(request("edition", [source]), workflow_binding=binding("new-run", [source]))
    assert caught.value.code == "conflict"


@pytest.mark.parametrize("projection", ["pending", "submitting", "unknown", "failed"])
def test_adopted_projection_must_be_done_before_send_reservation(store, projection):
    source = packet(store, "adopted")
    edition = ready(store, "edition", [source])
    store.projection_result(source["id"], projection)
    state = WorkflowState(store)
    with pytest.raises(StoreError):
        state.assert_publishable(edition["id"])
    with pytest.raises(StoreError):
        store.reserve_send(approval(edition))
    assert store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0
    assert store.get(edition["id"])["delivery_state"] == "not_requested"
    store.projection_result(source["id"], "done")
    state.assert_publishable(edition["id"])
    assert store.reserve_send(approval(edition))[1] is True


@pytest.mark.parametrize("required", [[], [{"id": "nonexistent-packet"}]])
def test_empty_or_missing_adopted_material_is_not_publishable(store, required):
    source = packet(store, "source")
    edition = ready(store, "edition", [source], required=required)
    with pytest.raises(StoreError):
        store.reserve_send(approval(edition))


@pytest.mark.parametrize("unused_state", ["pending", "submitting", "failed", "unknown"])
def test_unused_projection_does_not_block_adopted_confirmed_material(store, unused_state):
    adopted, unused = packet(store, "adopted"), packet(store, "unused")
    edition = ready(store, "edition", [adopted, unused], required=[adopted])
    store.projection_result(adopted["id"], "done")
    store.projection_result(unused["id"], unused_state)
    WorkflowState(store).assert_publishable(edition["id"])
    assert store.reserve_send(approval(edition))[1] is True


def test_dag_advance_ignores_unused_projection_failures(store, tmp_path):
    runs = RunRepository(store)
    run = runs.start(
        {"request_key": "run", "issue_date": "2026-09-06"},
        [],
        workflow_snapshot={"fixture": "not executed by this state-only test"},
    )
    adopted, unused = packet(store, "adopted"), packet(store, "unused")
    edition = ready(store, "edition", [adopted, unused], required=[adopted], run=run["id"])
    store.projection_result(adopted["id"], "done")
    store.projection_result(unused["id"], "unknown")
    runs.update(run["id"], state="editing", edition_id=edition["id"])
    pipeline = DagPipeline(
        runs,
        MockCollector(),
        tmp_path / "workspace",
        10,
        32,
        editor=CodexEditor(tmp_path / "unused-auth-path"),
    )
    assert pipeline.advance()
    assert runs.get(run["id"])["state"] == "ready"
    assert store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0


def test_same_date_new_edition_or_send_key_cannot_duplicate_reservation(store):
    source = packet(store, "adopted")
    first = ready(store, "edition-one", [source])
    second = ready(store, "edition-two", [source])
    store.projection_result(source["id"], "done")
    assert store.reserve_send(approval(first, "first-send"))[1] is True
    assert store.reserve_send(approval(first, "first-send"))[1] is False
    assert store.reserve_send(approval(first, "different-key"))[1] is False
    with pytest.raises(StoreError):
        store.reserve_send(approval(second, "second-send"))
    assert store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 1


def test_restart_unknown_send_is_not_reserved_again(store):
    source = packet(store, "adopted")
    edition = ready(store, "edition", [source])
    store.projection_result(source["id"], "done")
    assert store.reserve_send(approval(edition))[1] is True
    store.recover()
    assert store.get(edition["id"])["delivery_state"] == "unknown"
    assert store.reserve_send(approval(edition, "another-key"))[1] is False
