"""App factories are inert; each lifespan owns only its own resources."""

import asyncio
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from newsletter import lifecycle
from newsletter.app import create_app
from newsletter.preflight import PreflightError
from newsletter.settings import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "first",
        ingest_token="i" * 32,
        editor_token="e" * 32,
        send_token="s" * 32,
    )


def test_factory_does_not_open_storage_or_start_dependencies(settings, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Factory performed startup work")

    monkeypatch.setattr(lifecycle, "Store", unexpected)
    monkeypatch.setattr(lifecycle, "preflight", unexpected)
    app = create_app(settings)
    assert app.openapi()["info"]["title"] == "Personal Newsletter"
    assert not settings.data_dir.exists()


def test_two_apps_do_not_share_authentication_or_storage(settings):
    second = replace(
        settings,
        data_dir=settings.data_dir.with_name("second"),
        ingest_token="a" * 32,
        editor_token="b" * 32,
        send_token="c" * 32,
    )
    with TestClient(create_app(settings)) as first, TestClient(create_app(second)) as other:
        for client, own, foreign in ((first, settings, second), (other, second, settings)):
            assert client.post(
                "/v1/inbox/query",
                json={},
                headers={"Authorization": "Bearer " + own.editor_token},
            ).json() == {"packets": [], "next_cursor": ""}
            assert (
                client.post(
                    "/v1/inbox/query",
                    json={},
                    headers={"Authorization": "Bearer " + foreign.editor_token},
                ).status_code
                == 401
            )
        assert first.app.state.store is not other.app.state.store
        assert first.app.state.worker is not other.app.state.worker


def test_data_directory_lock_is_exclusive_and_released(settings):
    with TestClient(create_app(settings)) as first:
        with pytest.raises(RuntimeError, match="Only one service process"):
            with TestClient(create_app(settings)):
                pytest.fail("A second owner was allowed")
        assert first.get("/healthz").status_code == 200
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get("/healthz").status_code == 200


def test_preflight_failure_closes_storage_and_releases_lock(settings, monkeypatch):
    original = lifecycle.preflight
    captured = []

    async def unavailable(settings, *, store):
        captured.append(store)
        raise PreflightError("CODEX_CHECK_FAILED")

    monkeypatch.setattr(lifecycle, "preflight", unavailable)
    with pytest.raises(PreflightError):
        with TestClient(create_app(settings)):
            pytest.fail("Startup failure was ignored")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0].db.execute("SELECT 1")
    monkeypatch.setattr(lifecycle, "preflight", original)
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get("/healthz").status_code == 200


def test_shutdown_stops_worker_before_closing_its_store(settings, monkeypatch):
    events = []
    original_close = lifecycle.Store.close

    async def idle(worker):
        events.append("worker_started")
        try:
            await asyncio.Event().wait()
        finally:
            worker.store.db.execute("SELECT 1")
            events.append("worker_stopped")

    def close(store):
        events.append("store_closed")
        original_close(store)

    monkeypatch.setattr(lifecycle.Worker, "run", idle)
    monkeypatch.setattr(lifecycle.Store, "close", close)
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        assert events == ["worker_started"]
    assert events == ["worker_started", "worker_stopped", "store_closed"]
