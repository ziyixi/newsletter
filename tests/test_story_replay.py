"""Offline source-receipt continuation, never real research or mail."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from test_publication import DAY, result, task
from test_story_pipeline import rig_factory as _rig_factory
from test_usage import record_one
from test_workflow_content import candidate

from newsletter.app import create_app
from newsletter.contracts import canonical_json, content_hash
from newsletter.editor import MockEditor
from newsletter.settings import Settings
from newsletter.store import Store, StoreError
from newsletter.workflow.engine import NodeFailure, WorkflowEngine
from newsletter.workflow.nodes import EditorialNodes
from newsletter.workflow.story_editor import StoryEditor
from newsletter.workflow.story_replay import StoryReplay

rig_factory = _rig_factory


def failed_usage(stage):
    value = record_one()[-1]
    value.update(
        stage=stage,
        status="failed",
        usage=None,
        usage_events=0,
        turns_started=1,
        turns_completed=1,  # Failed completion after the provider's HTTP 400.
        turns_with_usage=0,
        partial=True,
    )
    return value


async def blocked_parent(rig, *, fatal=None, record_usage=True):
    rig.tasks = [task(1), task(2)]
    candidates = [
        candidate(id=selected["candidate_ids"][0], url=selected["source_urls"][0])
        for selected in rig.tasks
    ]
    outputs = {
        "history": {"candidates": [], "editions": [], "watchlist": []},
        "api_feed": {"candidates": [], "note": "Synthetic metadata"},
        "discovery": {"candidates": candidates, "note": "Synthetic discovery"},
        "deduplicate": {"candidates": candidates, "coverage": []},
        "selection": {"research_tasks": rig.tasks, "note": "Synthetic selection", "coverage": []},
        "story_plan": {"brief_tasks": rig.tasks, "deep_tasks": rig.tasks},
    }
    kinds = {node.id: node.type for node in rig.definition.nodes}

    async def execute(ctx):
        kind = kinds[ctx.node_id]
        if kind == "publish":
            raise NodeFailure("no_findings")
        if kind == "story_plan":
            rig.publications.save_plan(ctx.run_id, DAY, rig.tasks)
        if kind in {"story_brief", "story_deep"}:
            if record_usage:
                rig.pipeline.state.usage_sink(ctx.run_id)(
                    failed_usage(ctx.node_id + ":" + ctx.item_id)
                )
            if fatal:
                raise NodeFailure(fatal)
            value = {
                "story_id": ctx.item_id,
                "mode": "brief" if kind == "story_brief" else "deep",
                "content": None,
                "signal": None,
                "packets": [],
                "assessments": [],
                "issues": [
                    {
                        "round": "service",
                        "component": "body",
                        "claim": "",
                        "reason": "writer:unavailable",
                        "evidence": [],
                        "action": "research",
                    }
                ],
                "reason": "editor_unavailable",
                "provenance": {"packets_hash": content_hash([])},
            }
            rig.publications.save(ctx.run_id, ctx.item, value["mode"], value, issue_date=DAY)
            return value
        return deepcopy(outputs[kind])

    engine = WorkflowEngine(
        rig.pipeline.repository, {node.type: execute for node in rig.definition.nodes}
    )
    await engine.run(rig.run["id"])
    rig.pipeline.finish_graph(
        rig.run, rig.definition, rig.run["id"], rig.pipeline.repository.get(rig.run["id"])
    )
    assert rig.runs.get(rig.run["id"])["error_code"] == "no_publishable_content"


def request(key="explicit-story-restart"):
    return {"request_key": key, "issue_date": DAY}


def parent_receipts(rig):
    return deepcopy(
        {
            "run": rig.runs.get(rig.run["id"]),
            "snapshot": rig.runs.workflow_snapshot(rig.run["id"]),
            "graph": rig.pipeline.repository.get(rig.run["id"]),
            "attempts": rig.pipeline.repository.attempts(rig.run["id"]),
            "artifacts": rig.pipeline.repository.artifacts(rig.run["id"]),
            "results": rig.publications.results(rig.run["id"]),
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("fatal", [None, "configuration"])
async def test_fresh_child_reuses_only_upstream_inputs_without_provider_or_mail_replay(
    rig_factory, monkeypatch, fatal
):
    rig = rig_factory(expired=True)
    await blocked_parent(rig, fatal=fatal)
    parent = parent_receipts(rig)
    replay = StoryReplay(rig.store)
    child = replay.start(rig.run["id"], request())
    assert child["id"] != rig.run["id"]
    child_snapshot = rig.runs.workflow_snapshot(child["id"])
    original_inputs = parent["snapshot"]["inputs"]
    assert child_snapshot["definition"] == parent["snapshot"]["definition"]
    assert {
        key: value
        for key, value in child_snapshot["inputs"].items()
        if key not in {"started_at", "story_replay"}
    } == {key: value for key, value in original_inputs.items() if key != "started_at"}
    assert (
        datetime.now(UTC) - datetime.fromisoformat(child_snapshot["inputs"]["started_at"])
    ).total_seconds() < 10
    assert replay.start(rig.run["id"], request()) == child
    with pytest.raises(StoreError):
        replay.start(rig.run["id"], request("another-key"))

    async def forbidden(*args, **kwargs):
        raise AssertionError("Continuation cannot call fetch/discovery/selection/legacy editor")

    calls = []

    async def prepare(self, **values):
        calls.append((values["task"]["id"], values["mode"]))
        assert values["candidates"]
        return result(values["task"]["priority"], mode=values["mode"])

    monkeypatch.setattr(EditorialNodes, "execute", forbidden)
    monkeypatch.setattr(StoryEditor, "prepare", prepare)
    for _ in range(40):
        if (
            rig.runs.get(child["id"])["state"] != "queued"
            and rig.runs.get(child["id"])["state"] != "collecting"
        ):
            break
        assert await rig.pipeline.collect_next()
    assert rig.runs.get(child["id"])["state"] == "editing"
    assert calls == [
        ("story-1", "brief"),
        ("story-2", "brief"),
        ("story-1", "deep"),
        ("story-2", "deep"),
    ]
    assert rig.publications.plan(child["id"]) == rig.tasks
    assert parent_receipts(rig) == parent
    assert not rig.notion.calls
    assert rig.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0
    assert rig.store.db.execute("SELECT COUNT(*) FROM verification_sends").fetchone()[0] == 0
    assert replay.start(rig.run["id"], request())["state"] == "editing"
    with pytest.raises(StoreError):
        replay.start(child["id"], request("recursive-retry"))


@pytest.mark.asyncio
@pytest.mark.parametrize("fatal", ["authentication", "rate_limit", "timeout"])
async def test_account_failure_or_unknown_attempt_is_not_a_configuration_restart(
    rig_factory, fatal
):
    rig = rig_factory()
    await blocked_parent(rig, fatal=fatal)
    with pytest.raises(StoreError):
        StoryReplay(rig.store).start(rig.run["id"], request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "artifact",
        "instructions",
        "approved",
        "date",
        "edition",
        "usage",
        "input_hash",
        "map_hash",
        "incomplete_turn",
    ],
)
async def test_changed_or_ineligible_source_never_creates_a_child(rig_factory, mutation):
    rig = rig_factory()
    await blocked_parent(rig)
    payload = request()
    if mutation == "artifact":
        rig.store.db.execute(
            "UPDATE workflow_artifacts SET body=? WHERE run_id=? AND node_id='selection'",
            (canonical_json({"research_tasks": [], "note": "Unreviewed change"}), rig.run["id"]),
        )
    elif mutation == "instructions":
        rig.store.db.execute(
            "UPDATE collection_runs SET instructions='[]' WHERE id=?", (rig.run["id"],)
        )
    elif mutation == "approved":
        rig.publications.save(rig.run["id"], rig.tasks[0], "brief", result(), issue_date=DAY)
    elif mutation == "date":
        payload["issue_date"] = "2026-09-07"
    elif mutation == "edition":
        rig.runs.update(rig.run["id"], edition_id="already-edited")
    elif mutation == "input_hash":
        rig.store.db.execute(
            "UPDATE workflow_attempts SET input_hash=? WHERE run_id=? AND node_id='selection'",
            ("0" * 64, rig.run["id"]),
        )
    elif mutation == "map_hash":
        graph = rig.pipeline.repository.get(rig.run["id"])
        graph["nodes"]["discovery"]["map_hash"] = "0" * 64
        rig.store.db.execute(
            "UPDATE workflow_runs SET body=? WHERE id=?", (canonical_json(graph), rig.run["id"])
        )
    elif mutation == "incomplete_turn":
        row = rig.store.db.execute(
            "SELECT body FROM model_usage WHERE scope_id=? LIMIT 1", (rig.run["id"],)
        ).fetchone()
        import json

        value = json.loads(row[0])
        value["turns_completed"] = 0
        rig.pipeline.state.usage_sink(rig.run["id"])(value)
    else:
        value = record_one()[-1]
        value["stage"] = "briefs:story-1"
        rig.pipeline.state.usage_sink(rig.run["id"])(value)
    with pytest.raises(StoreError):
        StoryReplay(rig.store).start(rig.run["id"], payload)
    assert rig.store.db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_first_explicit_configuration_failure_before_usage_initialization_is_eligible(
    rig_factory,
):
    rig = rig_factory()
    await blocked_parent(rig, fatal="configuration", record_usage=False)
    child = StoryReplay(rig.store).start(rig.run["id"], request())
    assert child["state"] == "queued"


@pytest.mark.asyncio
async def test_concurrent_requests_create_only_one_child_and_reopen_does_not_reset_it(rig_factory):
    rig = rig_factory()
    await blocked_parent(rig)
    original = parent_receipts(rig)
    barrier = Barrier(2, timeout=5)

    def start():
        store = Store(rig.path / "newsletter.sqlite3", "mock")
        try:
            replay = StoryReplay(store)
            barrier.wait()
            return replay.start(rig.run["id"], request())
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(start), pool.submit(start)]
        children = [future.result(timeout=10) for future in futures]
    assert children[0] == children[1]
    assert rig.store.db.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0] == 2
    assert rig.store.db.execute("SELECT COUNT(*) FROM workflow_story_replays").fetchone()[0] == 1
    child = children[0]
    snapshot = rig.runs.workflow_snapshot(child["id"])
    reopened = Store(rig.path / "newsletter.sqlite3", "mock")
    try:
        reopened.recover()
        assert StoryReplay(reopened).start(rig.run["id"], request()) == child
    finally:
        reopened.close()
    assert rig.runs.workflow_snapshot(child["id"]) == snapshot
    assert parent_receipts(rig) == original


@pytest.mark.asyncio
async def test_source_hash_is_checked_again_when_child_locally_reuses_it(rig_factory):
    rig = rig_factory()
    await blocked_parent(rig)
    child = StoryReplay(rig.store).start(rig.run["id"], request())
    rig.store.db.execute(
        "UPDATE workflow_artifacts SET body='{}' WHERE run_id=? AND node_id='selection'",
        (rig.run["id"],),
    )
    assert await rig.pipeline.collect_next()
    assert rig.runs.get(child["id"])["state"] == "blocked"
    assert not rig.publications.results(child["id"])
    assert not rig.pipeline.state.usage(child["id"])["usage"]


@pytest.mark.asyncio
async def test_usage_keeps_parent_costs_and_missing_records_once_without_rewriting_them(
    rig_factory,
):
    rig = rig_factory()
    await blocked_parent(rig)
    usage = record_one()[-1]
    usage["stage"] = "discovery:synthetic"
    rig.pipeline.state.usage_sink(rig.run["id"])(usage)
    parent_rows = [
        tuple(row) for row in rig.store.db.execute("SELECT * FROM model_usage").fetchall()
    ]
    child = StoryReplay(rig.store).start(rig.run["id"], request())
    next_usage = record_one()[-1]
    next_usage["stage"] = "briefs:story-1"
    rig.pipeline.state.usage_sink(child["id"])(next_usage)
    summary = rig.pipeline.state.usage(child["id"])
    assert summary["usage"]["total_tokens"] == 240
    assert summary["invocations"] == 6
    assert summary["missing_invocations"] == 4 and summary["partial"]
    assert rig.pipeline.state.usage(rig.run["id"]) == summary
    assert [
        tuple(row)
        for row in rig.store.db.execute(
            "SELECT * FROM model_usage WHERE scope_id=?", (rig.run["id"],)
        )
    ] == parent_rows


@pytest.mark.asyncio
async def test_endpoint_is_editor_only_idempotent_and_never_sends(rig_factory):
    rig = rig_factory()
    await blocked_parent(rig)
    before = parent_receipts(rig)
    settings = Settings(
        data_dir=rig.path, editor_token="e" * 32, ingest_token="i" * 32, send_token="s" * 32
    )
    with TestClient(create_app(settings, editor=MockEditor(), start_worker=False)) as client:
        client.app.state.worker.pipeline = rig.pipeline
        url = f"/v1/runs/{rig.run['id']}/retry-stories"
        assert (
            client.post(
                url, json=request(), headers={"Authorization": "Bearer " + "s" * 32}
            ).status_code
            == 401
        )
        headers = {"Authorization": "Bearer " + "e" * 32}
        assert (
            client.post(
                "/v1/runs/missing/retry-stories", json=request(), headers=headers
            ).status_code
            == 404
        )
        assert (
            client.post(
                url, json={**request(), "issue_date": "2026-09-07"}, headers=headers
            ).status_code
            == 409
        )
        first = client.post(url, json=request(), headers=headers)
        assert first.status_code == 202, first.text
        child_id = first.json()["id"]
        assert child_id != rig.run["id"]
        assert client.post(url, json=request(), headers=headers).json() == first.json()
        assert client.post(url, json=request("another-key"), headers=headers).status_code == 409
        assert (
            client.post(
                f"/v1/runs/{child_id}/retry-stories", json=request("recursive"), headers=headers
            ).status_code
            == 409
        )
        assert not list(client.app.state.mail.directory.glob("*.eml"))
        assert parent_receipts(rig) == before
