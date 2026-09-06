"""Real durable publication tail with synthetic approved stories, no model or mail.

These tests deliberately fail the *new* topic DAG after saving a checked brief.
The legacy all-or-nothing recipe has separate tests and must not be mistaken for
coverage of deadline publication, local-first evidence, or topic dispositions.
"""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_publication import DAY, result, task

from newsletter.adapters import AdapterError
from newsletter.collection.collector import MockCollector
from newsletter.collection.repository import RunRepository
from newsletter.contracts import content_hash
from newsletter.editor import CodexEditor, MockEditor
from newsletter.settings import Settings
from newsletter.store import Store, StoreError
from newsletter.todofy import unavailable_digest
from newsletter.worker import Worker
from newsletter.workflow.definition import parse_definition
from newsletter.workflow.engine import NodeContext
from newsletter.workflow.nodes import EditorialNodes
from newsletter.workflow.pipeline import DagPipeline, freeze_workflow
from newsletter.workflow.publication import PublicationRepository
from newsletter.workflow.story_editor import StoryEditor
from newsletter.workflow.story_nodes import StoryNodes


class FailingNotion:
    def __init__(self):
        self.calls = []

    async def project(self, packet):
        self.calls.append(packet["id"])
        raise AdapterError("NOTION_REJECTED")


@pytest.fixture
def rig_factory(tmp_path, monkeypatch):
    stores = []

    async def forbidden(*args, **kwargs):
        raise AssertionError("A publication checkpoint must never run another model or collector")

    monkeypatch.setattr(CodexEditor, "execute", forbidden)
    monkeypatch.setattr(CodexEditor, "prepare", forbidden)
    monkeypatch.setattr(MockCollector, "collect", forbidden)

    def make(*, expired=False, legacy=False):
        directory = tmp_path / str(len(stores))
        store = Store(directory / "newsletter.sqlite3", "mock")
        stores.append(store)
        recipe = Path(
            str(
                files("newsletter").joinpath(
                    "workflows/legacy-daily.yaml" if legacy else "workflows/daily.yaml"
                )
            )
        )
        runs = RunRepository(store)
        pipeline = DagPipeline(
            runs,
            MockCollector(),
            directory / "collection",
            10,
            32,
            editor=CodexEditor(directory / "nonexistent-auth"),
            recipe_path=recipe,
        )
        instructions, snapshot = freeze_workflow(
            Settings(data_dir=directory, workflow_file=recipe), pipeline.state, DAY
        )
        if expired:
            snapshot["inputs"]["started_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        request = {"request_key": "synthetic-topics", "issue_date": DAY}
        run = runs.start(request, instructions, workflow_snapshot=snapshot)
        definition = parse_definition(snapshot["definition"])
        pipeline.repository.start(run["id"], definition, snapshot["inputs"])
        notion = FailingNotion()
        return SimpleNamespace(
            path=directory,
            store=store,
            runs=runs,
            pipeline=pipeline,
            publications=PublicationRepository(store),
            run=run,
            definition=definition,
            instructions=instructions,
            snapshot=snapshot,
            request=request,
            tasks=[task(1), task(2), task(3)],
            notion=notion,
            worker=Worker(store, MockEditor(), notion, directory / "editor", 10, pipeline=pipeline),
        )

    yield make
    for store in stores:
        store.close()


def seed_checkpoint(rig, *, approved=True):
    rig.publications.save_plan(rig.run["id"], DAY, rig.tasks)
    value = result(content=approved)
    rig.store.save_workflow_supplements(rig.run["id"], value["packets"])
    rig.publications.save(rig.run["id"], rig.tasks[0], "brief", value, issue_date=DAY)
    return value


def start_deep_attempt(rig):
    """Create a valid interrupted/failed attempt without SQL status surgery."""
    repository = rig.pipeline.repository
    outputs = {
        "history": {"candidates": [], "editions": []},
        "api_feed": {"candidates": []},
        "deduplicate": {"candidates": []},
        "selection": {"research_tasks": rig.tasks},
        "story_plan": {"brief_tasks": rig.tasks, "deep_tasks": rig.tasks[:1]},
    }
    for node in rig.definition.nodes:
        if node.type == "story_deep":
            repository.expand_map(rig.run["id"], node.id, rig.tasks[:1])
            attempt = repository.claim(rig.run["id"], node.id, rig.tasks[0]["id"], {})
            assert attempt
            rig.runs.update(rig.run["id"], state="collecting")
            return attempt
        if node.map:
            repository.expand_map(rig.run["id"], node.id, [])
            continue
        attempt = repository.claim(rig.run["id"], node.id, "", {})
        assert attempt
        repository.finish(attempt, "succeeded", outputs[node.type])
    raise AssertionError("New topic recipe has no deep stage")


def assert_partial_publication(rig):
    run = rig.runs.get(rig.run["id"])
    assert run["state"] == "editing", run
    assert run["edition_id"] and not run["error_code"]
    published = rig.publications.get_publication(run["id"])
    assert [story["story_id"] for story in published["coverage"]["stories"]] == [
        selected["id"] for selected in rig.tasks
    ]
    assert [story["disposition"] for story in published["coverage"]["stories"]] == [
        "brief",
        "deferred",
        "deferred",
    ]
    assert "Synthetic result 1" in str(published["draft"])
    assert "Synthetic research question 2" not in str(published["draft"])
    binding = rig.pipeline.state.edition(run["edition_id"])
    assert binding["projection_required"] is False
    assert binding["result"]["review"]["passed"] is True
    edition = rig.store.get(run["edition_id"])
    assert edition["publication"] == published["coverage"]
    assert edition["delivery_state"] == "not_requested"
    return edition, published


@pytest.mark.parametrize("terminal", ["failed", "unknown"])
def test_deep_terminal_attempt_preserves_approved_brief_and_all_topic_dispositions(
    rig_factory, terminal
):
    rig = rig_factory()
    checkpoint = seed_checkpoint(rig)
    attempt = start_deep_attempt(rig)
    if terminal == "failed":
        # An expired shared login is fatal even on an optional map.
        rig.pipeline.repository.finish(attempt, "failed", error_code="authentication")
    else:
        assert rig.pipeline.repository.recover() == 1
    status = rig.pipeline.repository.get(rig.run["id"])
    assert status["state"] == terminal
    attempts = deepcopy(rig.pipeline.repository.attempts(rig.run["id"]))
    assert rig.pipeline.finish_graph(rig.run, rig.definition, rig.run["id"], status)
    assert_partial_publication(rig)
    assert rig.publications.results(rig.run["id"]) == [checkpoint]
    assert rig.pipeline.repository.attempts(rig.run["id"]) == attempts
    assert not rig.notion.calls


@pytest.mark.asyncio
async def test_expired_budget_publishes_saved_brief_without_reset_or_another_model(rig_factory):
    rig = rig_factory(expired=True)
    seed_checkpoint(rig)
    frozen = deepcopy(rig.snapshot)
    assert await rig.pipeline.collect_next()
    assert_partial_publication(rig)
    assert rig.runs.workflow_snapshot(rig.run["id"]) == frozen
    assert not rig.pipeline.repository.attempts(rig.run["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("has_unapproved_result", [False, True])
async def test_no_checked_content_stays_blocked_without_mailing_empty_or_unverified_issue(
    rig_factory, has_unapproved_result
):
    rig = rig_factory(expired=True)
    if has_unapproved_result:
        seed_checkpoint(rig, approved=False)
    else:
        rig.publications.save_plan(rig.run["id"], DAY, rig.tasks)
    assert await rig.pipeline.collect_next()
    run = rig.runs.get(rig.run["id"])
    assert run["state"] == "blocked"
    assert run["error_code"] == "no_publishable_content"
    assert not run["edition_id"]
    assert rig.publications.get_publication(run["id"]) is None
    assert rig.store.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 0
    assert rig.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0
    assert len(rig.publications.pending_history("2026-09-07")) == 3


@pytest.mark.asyncio
async def test_local_publication_reaches_ready_despite_failed_notion_and_reserves_once(rig_factory):
    rig = rig_factory(expired=True)
    seed_checkpoint(rig)
    assert await rig.pipeline.collect_next()
    edition, _ = assert_partial_publication(rig)
    assert await rig.worker.step()  # Frozen edition rendering, no model.
    ready = rig.store.get(edition["id"])
    assert ready["state"] == "ready"
    assert rig.pipeline.advance()
    run = rig.runs.get(rig.run["id"])
    assert run["state"] == "ready", run
    assert not rig.notion.calls  # Projection was never a precondition.
    assert await rig.worker.step()
    assert rig.store.db.execute("SELECT projection FROM packets").fetchone()[0] == "failed"
    requested = {
        "id": ready["id"],
        "request_key": "send-test",
        "expected_render_hash": ready["rendered"]["render_hash"],
    }
    assert rig.store.reserve_send(requested)[1]
    assert not rig.store.reserve_send(requested)[1]
    assert rig.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 1
    assert rig.runs.get(rig.run["id"])["state"] == "ready"


@pytest.mark.asyncio
async def test_frozen_publication_reentry_is_idempotent_and_rejects_late_content(rig_factory):
    rig = rig_factory(expired=True)
    seed_checkpoint(rig)
    assert await rig.pipeline.collect_next()
    edition, original = assert_partial_publication(rig)
    frozen_hash = content_hash(original)
    rig.pipeline.publish_available(rig.runs.get(rig.run["id"]), rig.definition, reason="completed")
    again = rig.runs.get(rig.run["id"])
    assert again["edition_id"] == edition["id"]
    assert content_hash(rig.publications.get_publication(rig.run["id"])) == frozen_hash
    assert (
        rig.runs.start(rig.request, rig.instructions, workflow_snapshot=rig.snapshot)["id"]
        == rig.run["id"]
    )
    assert rig.store.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 1
    assert not rig.pipeline.repository.attempts(rig.run["id"])
    with pytest.raises(StoreError):
        rig.publications.save(
            rig.run["id"], rig.tasks[0], "deep", result(mode="deep"), issue_date=DAY
        )


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize(
    "state", ["queued", "collecting", "editing", "projecting", "blocked", "ready"]
)
def test_only_new_topic_collection_has_priority_over_background_projection(
    rig_factory, legacy, state
):
    rig = rig_factory(legacy=legacy)
    rig.runs.update(rig.run["id"], state=state)
    assert rig.pipeline.has_priority_work() is (not legacy and state in {"queued", "collecting"})


@pytest.mark.asyncio
async def test_legacy_deadline_does_not_adopt_new_local_first_policy(rig_factory):
    rig = rig_factory(expired=True, legacy=True)
    seed_checkpoint(rig)
    assert await rig.pipeline.collect_next()
    run = rig.runs.get(rig.run["id"])
    assert run["state"] == "blocked" and run["error_code"] == "workflow_deadline"
    assert not run["edition_id"]
    assert rig.publications.get_publication(run["id"]) is None


@pytest.mark.asyncio
async def test_approved_checkpoint_from_interrupted_story_handler_is_still_publishable(
    rig_factory, monkeypatch
):
    rig = rig_factory()
    rig.publications.save_plan(rig.run["id"], DAY, rig.tasks)
    checked = result()
    calls = []

    async def interrupted_after_checkpoint(self, **kwargs):
        calls.append(kwargs["task"]["id"])
        assert kwargs["is_fixture"] is True
        kwargs["on_checkpoint"](checked)
        # The review was already approved and durably saved before a later
        # optional component/provider operation stopped completing.
        raise TimeoutError()

    monkeypatch.setattr(StoryEditor, "prepare", interrupted_after_checkpoint)
    nodes = StoryNodes(rig.store, rig.definition, rig.pipeline.editor, rig.path / "jobs")
    context = NodeContext(
        run_id=rig.run["id"],
        node_id="briefs",
        item_id=rig.tasks[0]["id"],
        params={},
        inputs={"candidates": {"candidates": []}},
        run_inputs=rig.snapshot["inputs"],
        item=rig.tasks[0],
    )
    with pytest.raises(TimeoutError):
        await nodes.execute("story_brief", context, rig.path / "story-workspace")
    assert rig.publications.results(rig.run["id"]) == [checked]
    assert rig.store.db.execute("SELECT COUNT(*) FROM packets").fetchone()[0] == 1
    rig.pipeline.publish_available(rig.run, rig.definition, reason="deadline")
    assert_partial_publication(rig)
    assert calls == [rig.tasks[0]["id"]]


@pytest.mark.asyncio
async def test_complete_default_topic_graph_freezes_all_briefs_before_deepening_and_renders(
    rig_factory, monkeypatch
):
    rig = rig_factory()
    candidates = [
        {
            "id": f"candidate-{number}",
            "title": f"Synthetic discovery {number}",
            "summary": "Synthetic discovery metadata, not reviewed evidence.",
            "why_now": "Synthetic new result.",
            "url": f"https://example.org/research/{number}",
            "published_at": DAY,
        }
        for number in range(1, 4)
    ]
    calls = []

    async def synthetic_discovery(self, kind, ctx, path):
        if kind == "history":
            return {"candidates": [], "editions": [], "watchlist": []}
        if kind == "api_feed":
            return {"candidates": []}
        if kind in {"discovery", "deduplicate"}:
            return {"candidates": deepcopy(candidates)}
        if kind == "selection":
            return {"research_tasks": deepcopy(rig.tasks)}
        raise AssertionError("Topic graph must not invoke legacy composition or whole-issue review")

    async def synthetic_story(self, **kwargs):
        selected, mode = kwargs["task"], kwargs["mode"]
        number = int(selected["id"].rsplit("-", 1)[1])
        calls.append((mode, selected["id"]))
        if mode == "deep":
            assert calls[:3] == [("brief", item["id"]) for item in rig.tasks]
            assert kwargs["prior"]["mode"] == "brief"
            assert kwargs["prior"]["content"]["story_id"] == selected["id"]
            assert kwargs["packets"] == kwargs["prior"]["packets"]
        else:
            assert kwargs["prior"] is None
        assert kwargs["is_fixture"] is True
        value = result(number, mode)
        kwargs["on_checkpoint"](value)
        return value

    monkeypatch.setattr(EditorialNodes, "execute", synthetic_discovery)
    monkeypatch.setattr(StoryEditor, "prepare", synthetic_story)
    for _ in range(60):
        if rig.runs.get(rig.run["id"])["state"] == "ready":
            break
        assert await rig.worker.step()
    run = rig.runs.get(rig.run["id"])
    assert run["state"] == "ready", run
    assert len(calls) == 6
    assert calls == [(mode, item["id"]) for mode in ("brief", "deep") for item in rig.tasks]
    assert (
        len(rig.publications.results(run["id"])) == 6
    )  # Duplicate callback/final save is idempotent.
    graph = rig.pipeline.repository.get(run["id"])
    assert graph["state"] == "succeeded"
    assert len(graph["nodes"]) == 9
    edition = rig.store.get(run["edition_id"])
    assert edition["state"] == "ready"
    assert [story["disposition"] for story in edition["publication"]["stories"]] == [
        "deep",
        "deep",
        "brief",
    ]
    assert edition["publication"]["mode"] == "complete"
    assert "Synthetic result 1" in edition["rendered"]["text"]
    assert "Synthetic result 2" in edition["rendered"]["text"]
    assert "Synthetic result 3" in edition["rendered"]["text"]
    assert not rig.notion.calls
    assert rig.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0
    attempts = deepcopy(rig.pipeline.repository.attempts(run["id"]))
    while await rig.worker.step():
        pass  # Only background projections remain; none retries or edits the issue.
    assert len(calls) == 6
    assert rig.pipeline.repository.attempts(run["id"]) == attempts
    assert len(rig.notion.calls) == len(set(rig.notion.calls)) == 4


@pytest.mark.asyncio
async def test_restart_during_local_render_recovers_same_edition_and_reuses_completed_personal_digest(
    rig_factory, monkeypatch
):
    rig = rig_factory(expired=True)
    seed_checkpoint(rig)
    assert await rig.pipeline.collect_next()
    edition, publication = assert_partial_publication(rig)
    binding = deepcopy(rig.pipeline.state.edition(edition["id"]))
    assert rig.store.claim()[0]["id"] == edition["id"]
    personal = unavailable_digest()
    rig.store.finish(edition["id"], personal_digest=personal)
    rig.store.recover()
    rig.runs.recover()
    rig.pipeline.recover()
    assert rig.store.get(edition["id"])["state"] == "queued"

    async def no_second_todofy(edition):
        raise AssertionError("Completed private summary must not be regenerated on local resume")

    monkeypatch.setattr(rig.worker, "personal_digest", no_second_todofy)
    assert await rig.worker.step()
    assert rig.pipeline.advance()
    ready = rig.store.get(edition["id"])
    assert ready["state"] == "ready"
    assert ready["personal_digest"] == personal
    assert rig.runs.get(rig.run["id"])["state"] == "ready"
    assert rig.pipeline.state.edition(edition["id"]) == binding
    assert rig.publications.get_publication(rig.run["id"]) == publication
    assert rig.store.db.execute("SELECT COUNT(*) FROM editions").fetchone()[0] == 1
    assert not rig.pipeline.repository.attempts(rig.run["id"])


@pytest.mark.asyncio
async def test_graceful_cancellation_during_render_uses_same_safe_resume_policy(
    rig_factory, monkeypatch
):
    rig = rig_factory(expired=True)
    seed_checkpoint(rig)
    assert await rig.pipeline.collect_next()
    edition, _ = assert_partial_publication(rig)
    entered = asyncio.Event()
    original = asyncio.to_thread
    personal_calls = []

    async def personal(edition):
        personal_calls.append(edition["id"])
        return unavailable_digest()

    async def paused_render(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(rig.worker, "personal_digest", personal)
    monkeypatch.setattr("newsletter.worker.asyncio.to_thread", paused_render)
    work = asyncio.create_task(rig.worker.step())
    await asyncio.wait_for(entered.wait(), 2)
    work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work
    assert rig.store.get(edition["id"])["state"] == "queued"
    assert "personal_digest" in rig.store.get(edition["id"])
    monkeypatch.setattr("newsletter.worker.asyncio.to_thread", original)
    assert await rig.worker.step()
    assert rig.store.get(edition["id"])["state"] == "ready"
    assert personal_calls == [edition["id"]]


@pytest.mark.parametrize("interruption", ["crash", "cancel"])
@pytest.mark.parametrize(
    "unsafe",
    [
        "legacy_policy",
        "missing_publication",
        "wrong_publication_date",
        "changed_publication",
        "changed_binding",
        "missing_evidence",
        "changed_evidence",
        "unknown_send",
        "same_date_send",
        "render_already_frozen",
        "already_failed",
    ],
)
def test_local_render_recovery_never_weakens_frozen_evidence_legacy_or_send_guards(
    rig_factory, interruption, unsafe
):
    rig = rig_factory(expired=True)
    seed_checkpoint(rig)
    asyncio.run(rig.pipeline.collect_next())
    edition, _ = assert_partial_publication(rig)
    rig.store.claim()
    identifier = edition["id"]
    if unsafe == "legacy_policy":
        rig.store.db.execute("UPDATE workflow_editions SET projection_required=1")
    elif unsafe == "missing_publication":
        rig.store.db.execute("DELETE FROM publication_snapshots")
    elif unsafe == "wrong_publication_date":
        rig.store.db.execute("UPDATE publication_snapshots SET issue_date='2026-09-07'")
    elif unsafe == "changed_publication":
        rig.store.db.execute("UPDATE publication_snapshots SET digest='incorrect'")
    elif unsafe == "changed_binding":
        rig.store.db.execute("UPDATE workflow_editions SET editor_result='{}'")
    elif unsafe == "missing_evidence":
        rig.store.db.execute("DELETE FROM packets")
    elif unsafe == "changed_evidence":
        rig.store.db.execute("UPDATE packets SET body='{}'")
    elif unsafe in {"unknown_send", "same_date_send"}:
        rig.store.db.execute(
            "INSERT INTO sends VALUES(?,?,?,?)",
            (
                DAY,
                identifier if unsafe == "unknown_send" else "other-edition",
                "test-send",
                "frozen-hash",
            ),
        )
        if unsafe == "unknown_send":
            rig.store.finish(identifier, delivery_state="unknown")
    elif unsafe == "render_already_frozen":
        rig.store.finish(
            identifier,
            rendered={"html": "frozen", "text": "frozen", "chart_png": "", "render_hash": "hash"},
        )
    else:
        rig.store.finish(identifier, state="failed", error_code="editor_invalid_result")
    if interruption == "crash":
        rig.store.recover()
    else:
        rig.store.interrupt_preparation(identifier)
    rejected = rig.store.get(identifier)
    assert rejected["state"] == "failed"
    if unsafe == "unknown_send":
        assert rejected["delivery_state"] == "unknown"
    if unsafe == "already_failed":
        assert rejected["error_code"] == "editor_invalid_result"
    if unsafe == "render_already_frozen":
        assert rejected["rendered"]["render_hash"] == "hash"
