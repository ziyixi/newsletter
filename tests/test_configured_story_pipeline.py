"""Real config/DAG/SQLite/publication/render integration; synthetic provider boundary.

No real API, research, Notion write or email is permitted. Unlike a node-only
test, this exercises the installed bundle and the normal serialized worker.
"""

import json
import sqlite3
from copy import deepcopy

import pytest
import yaml
from fastapi.testclient import TestClient
from test_news_first_policy import news, paper
from test_publication import DAY, result, story
from test_workflow_content import discovered

from newsletter import lifecycle
from newsletter.app import create_app
from newsletter.collection.collector import MockCollector
from newsletter.collection.repository import RunRepository
from newsletter.content_config import (
    ContentConfigError,
    build_snapshot,
    install_snapshot,
    load_active,
    packaged_snapshot,
)
from newsletter.editor import CodexEditor, MockEditor
from newsletter.preflight import PreflightReport
from newsletter.settings import Settings
from newsletter.store import Store
from newsletter.worker import Worker
from newsletter.workflow.pipeline import DagPipeline, freeze_workflow
from newsletter.workflow.sources import MetadataResult, PublicMetadataFeed
from newsletter.workflow.story_editor import StoryEditor


class ForbiddenNotion:
    async def project(self, packet):
        raise AssertionError(
            "Configuration integration must never write to Notion"
        )


@pytest.mark.parametrize("state", ["missing", "corrupt", "valid"])
def test_live_lifespan_checks_active_configuration_before_advertising_readiness(
    tmp_path, monkeypatch, state
):
    root = tmp_path / "config"
    if state != "missing":
        install_snapshot(root, packaged_snapshot())
        if state == "corrupt":
            (root / "active.json").write_text("{}")
    settings = Settings(
        data_dir=tmp_path / "service",
        mode="live",
        editor_backend="codex",
        codex_home=tmp_path / "nonexistent-fixture-auth",
        workflow_backend="dag",
        content_config_dir=root,
        notion_backend="disabled",
        mail_backend="fake",
        ingest_token="i" * 32,
        editor_token="e" * 32,
        send_token="s" * 32,
    )
    opened = []

    async def offline_provider_preflight(settings, *, store):
        opened.append(store)
        return PreflightReport(("offline_test_boundary",), ())

    async def forbidden(*args, **kwargs):
        raise AssertionError(
            "Startup-only test cannot call a model or run a worker"
        )

    monkeypatch.setattr(lifecycle, "preflight", offline_provider_preflight)
    monkeypatch.setattr(CodexEditor, "execute", forbidden)
    monkeypatch.setattr(Worker, "run", forbidden)
    app = create_app(settings, start_worker=False)
    if state == "valid":
        with TestClient(app) as client:
            assert client.get("/healthz").status_code == 200
            assert isinstance(app.state.worker.pipeline, DagPipeline)
            assert app.state.worker_task is None
            assert (
                app.state.store.db.execute(
                    "SELECT COUNT(*) FROM collection_runs"
                ).fetchone()[0]
                == 0
            )
    else:
        with pytest.raises(ContentConfigError):
            with TestClient(app):
                pytest.fail(
                    "Missing or corrupt active configuration advertised readiness"
                )
        assert not hasattr(app.state, "worker")
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].db.execute("SELECT 1")


@pytest.mark.parametrize("excess_research", [False, True])
async def test_installed_config_drives_whole_topic_pipeline_and_survives_midrun_switch(
    tmp_path, monkeypatch, excess_research
):
    config_root = tmp_path / "config"
    packaged = packaged_snapshot()
    first_files = dict(packaged["files"])
    first_files["prompts/discovery.md"] += "\nDISCOVERY CONFIG A"
    first_files["prompts/selection.md"] += "\nSELECTION CONFIG A"
    first_files["policy/editorial.md"] += "\nWRITING CONFIG A"
    first_files["templates/edition.html.j2"] = first_files[
        "templates/edition.html.j2"
    ].replace("THE DAILY BRIEF", "CONFIG A DAILY BRIEF")
    first = build_snapshot(first_files, "a" * 40)
    install_snapshot(config_root, first)

    second_files = dict(first_files)
    second_files["editorial.yaml"] = yaml.safe_dump(
        {
            "max_public_items": 1,
            "max_research_items": 0,
            "max_deep": 0,
            "max_research_candidates": 0,
        }
    )
    for name in (
        "prompts/discovery.md",
        "prompts/selection.md",
        "policy/editorial.md",
    ):
        second_files[name] = second_files[name].replace("CONFIG A", "CONFIG B")
    second_files["templates/edition.html.j2"] = second_files[
        "templates/edition.html.j2"
    ].replace("CONFIG A DAILY BRIEF", "CONFIG B DAILY BRIEF")
    second = build_snapshot(second_files, "b" * 40)

    store = Store(tmp_path / "state.sqlite3", "mock")
    provider_calls, writing_calls = [], []
    switched = False

    async def forbidden(*args, **kwargs):
        raise AssertionError(
            "No legacy collector, whole-issue editor, external API or email"
        )

    async def empty_public_metadata(self, issue_date):
        return MetadataResult([], ["Synthetic offline metadata boundary"])

    async def provider(self, prompt, schema, instructions, workspace):
        nonlocal switched
        value = json.loads(prompt)
        provider_calls.append((value, schema, instructions))
        if "candidates" in schema["properties"]:
            assert (
                "DISCOVERY CONFIG A" in instructions
                and "DISCOVERY CONFIG B" not in instructions
            )
            direction = value["direction"]
            candidates = (
                [news(number) for number in range(1, 6)]
                if direction == "03-world"
                else [paper(number) for number in range(1, 6)]
                if direction == "08-llm-architectures"
                else []
            )
            output = json.loads(discovered(*candidates))
            for candidate in output["candidates"]:
                # A paper cannot masquerade as news even if both model stages
                # say news. The parser uses the candidate's publication identity.
                candidate.update(
                    editorial_kind="news",
                    change_basis="A concrete availability change was announced.",
                )
            if not switched:
                install_snapshot(config_root, second)
                switched = True
            return json.dumps(output), {c["url"] for c in candidates}, True
        assert "research_tasks" in schema["properties"]
        assert (
            "SELECTION CONFIG A" in instructions
            and "SELECTION CONFIG B" not in instructions
        )
        assert value["max_tasks"] == 6
        assert schema["properties"]["research_tasks"]["maxItems"] == 6
        assert value["editorial_budget"] == {
            "max_public_items": 6,
            "max_research_items": 1,
            "max_deep": 1,
        }
        candidates = value["candidates_untrusted"]
        assert len(candidates) == 10
        kinds = value["candidate_classifications"]
        papers = [c for c in candidates if kinds[c["id"]]["kind"] == "research"]
        events = [c for c in candidates if kinds[c["id"]]["kind"] == "news"]
        assert len(papers) == len(events) == 5
        chosen = (
            papers[:2] + events[:4] if excess_research else events + papers[:1]
        )
        tasks = [
            {
                "id": f"story-{number}",
                "candidate_ids": [c["id"]],
                "priority": number,
                "question": f"What changed in {c['title']}?",
                "why": "A specific change merits investigation.",
                "evidence_context": c["summary"],
                "source_urls": [c["url"]],
                "editorial_kind": "news",
            }
            for number, c in enumerate(chosen, 1)
        ]
        return (
            json.dumps(
                {"research_tasks": tasks, "note": "Synthetic selection fixture"}
            ),
            set(),
            False,
        )

    async def prepare_story(self, **kwargs):
        task, mode = kwargs["task"], kwargs["mode"]
        number = int(task["id"].rsplit("-", 1)[1])
        assert "WRITING CONFIG A" in kwargs["policy"]["editorial.md"]
        assert "WRITING CONFIG B" not in kwargs["policy"]["editorial.md"]
        assert (
            "公共选题最多6项，研究主体最多1项，深读最多1项"
            in kwargs["policy"]["editorial.md"]
        )
        if mode == "deep":
            assert len(
                [call for call in writing_calls if call[0] == "brief"]
            ) == (5 if excess_research else 6)
            assert kwargs["prior"]["mode"] == "brief"
        writing_calls.append((mode, task["id"]))
        candidate = kwargs["candidates"][0]
        content = story(
            number,
            title=candidate["title"],
            kind="ai_ml" if "arxiv.org" in candidate["url"] else "world",
        )
        value = result(number, mode, content=content)
        kwargs["on_checkpoint"](value)
        return value

    monkeypatch.setattr(PublicMetadataFeed, "fetch", empty_public_metadata)
    monkeypatch.setattr(CodexEditor, "execute", provider)
    monkeypatch.setattr(CodexEditor, "prepare", forbidden)
    monkeypatch.setattr(MockEditor, "prepare", forbidden)
    monkeypatch.setattr(MockCollector, "collect", forbidden)
    monkeypatch.setattr(StoryEditor, "prepare", prepare_story)
    try:
        runs = RunRepository(store)
        pipeline = DagPipeline(
            runs,
            MockCollector(),
            tmp_path / "collection",
            10,
            32,
            editor=CodexEditor(tmp_path / "nonexistent-auth"),
        )
        settings = Settings(
            workflow_backend="dag", content_config_dir=config_root
        )
        instructions, snapshot = freeze_workflow(settings, pipeline.state, DAY)
        frozen = deepcopy(snapshot)
        run = runs.start(
            {"request_key": "installed-config-e2e", "issue_date": DAY},
            instructions,
            workflow_snapshot=snapshot,
        )
        worker = Worker(
            store,
            MockEditor(),
            ForbiddenNotion(),
            tmp_path / "editor",
            10,
            pipeline=pipeline,
            skip_packet_projection=True,
        )
        for _ in range(80):
            if runs.get(run["id"])["state"] in {"ready", "blocked", "failed"}:
                break
            assert await worker.step()
        completed = runs.get(run["id"])
        assert completed["state"] == "ready", completed
        graph = pipeline.repository.get(run["id"])
        assert graph["state"] == "succeeded"
        selection = pipeline.repository.output(run["id"], "selection")
        plan = pipeline.repository.output(run["id"], "story_plan")
        expected_count = 5 if excess_research else 6
        assert len(selection["research_tasks"]) == expected_count
        assert (
            sum(
                kind == "research"
                for kind in selection["task_classifications"].values()
            )
            == 1
        )
        assert len(selection["omitted_tasks"]) == (1 if excess_research else 0)
        if excess_research:
            assert selection["omitted_tasks"][0]["reason"] == "research_quota"
        assert (
            len(plan["brief_tasks"]) == expected_count
            and len(plan["deep_tasks"]) == 1
        )
        assert len([call for call in writing_calls if call[0] == "deep"]) == 1
        edition = store.get(completed["edition_id"])
        assert (
            edition["state"] == "ready"
            and edition["delivery_state"] == "not_requested"
        )
        assert len(edition["draft"]["sections"]) == expected_count
        assert (
            sum(
                s["disposition"] == "deep"
                for s in edition["publication"]["stories"]
            )
            == 1
        )
        assert "CONFIG A DAILY BRIEF" in edition["rendered"]["html"]
        assert "CONFIG B DAILY BRIEF" not in edition["rendered"]["html"]
        assert (
            sum(
                section["kind"] == "ai_ml"
                for section in edition["draft"]["sections"]
            )
            == 1
        )
        assert (
            len(provider_calls) == 9
        )  # Eight bounded retrievals, one selection.
        assert load_active(config_root) == second
        assert runs.workflow_snapshot(run["id"]) == frozen
        assert (
            pipeline.repository.snapshot(run["id"])["inputs"]["content_config"]
            == first
        )
        _, next_snapshot = freeze_workflow(
            settings, pipeline.state, "2026-09-07"
        )
        assert next_snapshot["inputs"]["content_config"] == second
        assert store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0
        assert (
            store.db.execute(
                "SELECT COUNT(*) FROM verification_sends"
            ).fetchone()[0]
            == 0
        )
    finally:
        store.close()
