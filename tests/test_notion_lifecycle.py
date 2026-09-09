"""V2 composition and operator diagnostics do not run models or send email."""

import asyncio
from dataclasses import replace

import pytest
from fastapi import FastAPI

from newsletter import lifecycle
from newsletter.adapters import DisabledNotion
from newsletter.editor import MockEditor
from newsletter.notion_cli import status
from newsletter.preflight import PreflightReport
from newsletter.settings import Settings
from newsletter.store import Store
from newsletter.workflow.pipeline import freeze_workflow
from newsletter.workflow.state import WorkflowState


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "live",
        mode="live",
        editor_backend="codex",
        workflow_backend="dag",
        notion_backend="notion",
        notion_token="synthetic-notion-token-for-offline-test",
        notion_materials_data_source_id="11111111-1111-4111-8111-111111111111",
        notion_editions_data_source_id="22222222-2222-4222-8222-222222222222",
        codex_home=tmp_path / "auth",
    )


async def test_two_consumers_stop_before_store_and_old_projection_is_not_claimed(
    settings, monkeypatch
):
    events = []

    async def checked(*args, **kwargs):
        return PreflightReport((), ())

    async def idle_worker(self):
        events.append("worker-start")
        try:
            await asyncio.Event().wait()
        finally:
            self.store.db.execute("SELECT 1")
            events.append("worker-stop")

    async def idle_sync(self):
        events.append("sync-start")
        try:
            await asyncio.Event().wait()
        finally:
            self.journal.store.db.execute("SELECT 1")
            events.append("sync-stop")

    monkeypatch.setattr(lifecycle, "preflight", checked)
    monkeypatch.setattr(lifecycle.Worker, "run", idle_worker)
    monkeypatch.setattr(lifecycle.NotionSync, "run", idle_sync)
    app = FastAPI()
    async with lifecycle.service_lifespan(
        app, settings=settings, editor=MockEditor()
    ):
        await asyncio.sleep(0)
        assert events == ["worker-start", "sync-start"]
        assert isinstance(app.state.worker.notion, DisabledNotion)
        assert app.state.worker.skip_packet_projection
        before = (settings.data_dir / "newsletter.sqlite3").read_bytes()
        assert status(settings.data_dir / "newsletter.sqlite3")["enabled"]
        assert (settings.data_dir / "newsletter.sqlite3").read_bytes() == before
        assert not app.state.store.db.execute("SELECT 1 FROM sends").fetchone()
    assert events == ["worker-start", "sync-start", "sync-stop", "worker-stop"]


async def test_destination_failure_does_not_leave_content_worker_running(
    settings, monkeypatch
):
    async def checked(*args, **kwargs):
        return PreflightReport((), ())

    async def forbidden(*args, **kwargs):
        pytest.fail("A consumer started before initialization completed")

    monkeypatch.setattr(lifecycle, "preflight", checked)
    app = FastAPI()
    async with lifecycle.service_lifespan(
        app, settings=settings, start_worker=False
    ):
        pass
    monkeypatch.setattr(lifecycle.Worker, "run", forbidden)
    with pytest.raises(ValueError, match="explicit migration"):
        async with lifecycle.service_lifespan(
            app, settings=replace(settings, notion_archive_private=True)
        ):
            pytest.fail("Changed audience/privacy was silently adopted")


def test_status_missing_database_never_creates_it(tmp_path):
    import sqlite3

    path = tmp_path / "absent.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        status(path)
    assert not path.exists()


def test_legacy_recipe_is_rejected_for_v2_before_freezing(
    settings, tmp_path, monkeypatch
):
    from newsletter.workflow import pipeline

    with_store = Store(tmp_path / "source.sqlite3", "live")
    try:
        monkeypatch.setattr(
            pipeline, "is_story_recipe", lambda definition: False
        )
        with pytest.raises(ValueError, match="story publication"):
            freeze_workflow(settings, WorkflowState(with_store), "2026-09-07")
    finally:
        with_store.close()
