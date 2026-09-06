"""Explicit corrected-issue tests cannot erase or bypass normal delivery receipts."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from newsletter.app import create_app
from newsletter.editor import MockEditor
from newsletter.settings import Settings
from newsletter.store import Store, StoreError


def auth(role="send"):
    return {"Authorization": "Bearer " + {"send": "s", "editor": "e", "ingest": "i"}[role] * 32}


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        ingest_token="i" * 32,
        editor_token="e" * 32,
        send_token="s" * 32,
    )
    with TestClient(create_app(settings, editor=MockEditor(), start_worker=False)) as value:
        yield value


def issue(client, key):
    packet = client.post(
        "/v1/packets",
        headers=auth("ingest"),
        json={
            "request_key": "packet",
            "workflow_id": "verification-offline-test",
            "content": {
                "title": "Fixture",
                "body": "Synthetic offline source.",
                "sources": [
                    {
                        "id": "source",
                        "title": "Fixture source",
                        "url": "https://example.org/fixture",
                        "excerpt": "Fixture.",
                        "access_scope": "full_text",
                    }
                ],
            },
        },
    ).json()
    queued = client.post(
        "/v1/editions",
        headers=auth("editor"),
        json={
            "request_key": key,
            "issue_date": "2026-09-06",
            "packet_ids": [packet["id"]],
        },
    ).json()
    client.portal.call(client.app.state.worker.step)
    result = client.get(f"/v1/editions/{queued['id']}", headers=auth()).json()
    assert result["state"] == "ready"
    return result


def send(client, edition, *, verification=False, key="normal", role="send", digest=None):
    suffix = "send-verification" if verification else "send"
    return client.post(
        f"/v1/editions/{edition['id']}/{suffix}",
        headers=auth(role),
        json={
            "id": edition["id"],
            "request_key": key,
            "expected_render_hash": digest or edition["rendered"]["render_hash"],
        },
    )


def test_verification_is_separate_idempotent_and_preserves_daily_guard(client):
    original = issue(client, "original")
    assert send(client, original).json()["delivery_state"] == "simulated"
    old_receipt = tuple(client.app.state.store.db.execute("SELECT * FROM sends").fetchone())
    corrected = issue(client, "corrected")
    assert send(client, corrected, key="normal-again").status_code == 409
    assert send(client, corrected, verification=True, role="editor").status_code == 401
    assert send(client, corrected, verification=True, digest="0" * 64).status_code == 409
    first = send(client, corrected, verification=True, key="explicit-correction")
    assert first.status_code == 200 and first.json()["delivery_state"] == "simulated"
    assert (
        send(client, corrected, verification=True, key="explicit-correction").json() == first.json()
    )
    assert send(client, corrected, verification=True, key="another-key").json() == first.json()
    third = issue(client, "third")
    assert send(client, third, verification=True, key="third-key").status_code == 409
    assert send(client, third, key="normal-third").status_code == 409
    assert tuple(client.app.state.store.db.execute("SELECT * FROM sends").fetchone()) == old_receipt
    assert (
        client.app.state.store.db.execute("SELECT COUNT(*) FROM verification_sends").fetchone()[0]
        == 1
    )
    assert len(list(client.app.state.mail.directory.glob("*.eml"))) == 2


@pytest.mark.parametrize("state", ["not_requested", "submitting", "rejected", "unknown"])
def test_verification_cannot_bypass_unconfirmed_original(client, state):
    original = issue(client, "original")
    if state != "not_requested":
        assert send(client, original).status_code == 200
        client.app.state.store.finish(original["id"], delivery_state=state)
    corrected = issue(client, "corrected")
    assert send(client, corrected, verification=True).status_code == 409
    assert (
        client.app.state.store.db.execute("SELECT COUNT(*) FROM verification_sends").fetchone()[0]
        == 0
    )


def test_verification_never_resends_original_edition(client):
    original = issue(client, "original")
    assert send(client, original).status_code == 200
    assert send(client, original, verification=True).status_code == 409


def test_ambiguous_verification_stays_unknown_after_recovery(client):
    original = issue(client, "original")
    assert send(client, original).status_code == 200
    corrected = issue(client, "corrected")

    class UncertainMail:
        calls = 0

        async def send(self, edition, idempotency_key):
            self.calls += 1
            raise TimeoutError("Private provider diagnostic must not appear")

    adapter = UncertainMail()
    client.app.state.mail = adapter
    first = send(client, corrected, verification=True, key="verify")
    assert first.json()["delivery_state"] == "unknown"
    client.app.state.store.recover()
    assert (
        send(client, corrected, verification=True, key="different").json()["delivery_state"]
        == "unknown"
    )
    assert adapter.calls == 1
    assert "Private provider" not in first.text


def test_verification_checks_path_and_key_binding(client):
    original = issue(client, "original")
    assert send(client, original).status_code == 200
    corrected = issue(client, "corrected")
    assert send(client, corrected, verification=True, key="verification").status_code == 200
    third = issue(client, "third")
    assert send(client, third, verification=True, key="verification").status_code == 409
    assert (
        client.post(
            f"/v1/editions/{third['id']}/send-verification",
            headers=auth(),
            json={
                "id": corrected["id"],
                "request_key": "verification",
                "expected_render_hash": corrected["rendered"]["render_hash"],
            },
        ).status_code
        == 409
    )


@pytest.mark.parametrize("same_edition", [True, False])
def test_simultaneous_verification_reservations_use_one_durable_receipt(client, same_edition):
    original = issue(client, "original")
    assert send(client, original).status_code == 200
    corrected = issue(client, "corrected")
    rival = corrected if same_edition else issue(client, "competing-correction")
    store = client.app.state.store
    original_receipt = tuple(store.db.execute("SELECT * FROM sends").fetchone())
    database = Path(store.db.execute("PRAGMA database_list").fetchone()[2])
    barrier = Barrier(2, timeout=5)

    def reserve(edition, key):
        # Separate connections exercise SQLite's transaction boundary, not just
        # one app instance's Python lock. No mail provider is called in this test.
        connection = Store(database, "mock")
        try:
            barrier.wait()
            try:
                value, first = connection.reserve_verification_send(
                    {
                        "id": edition["id"],
                        "request_key": key,
                        "expected_render_hash": edition["rendered"]["render_hash"],
                    }
                )
                return value, first
            except StoreError as exc:
                return None, exc.code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(reserve, corrected, "verification-a"),
            executor.submit(reserve, rival, "verification-b"),
        ]
        outcomes = [future.result(timeout=10) for future in futures]
    flags = [first for _, first in outcomes]
    assert flags.count(True) == 1
    assert flags.count(False if same_edition else "conflict") == 1
    accepted = next(edition for edition, first in outcomes if first is True)
    assert accepted["delivery_state"] == "submitting"
    assert store.db.execute("SELECT COUNT(*) FROM verification_sends").fetchone()[0] == 1
    assert tuple(store.db.execute("SELECT * FROM sends").fetchone()) == original_receipt

    # A crash after reservation has an unknown outcome, even with a fresh
    # connection and a different key. It cannot authorize another provider call.
    reopened = Store(database, "mock")
    try:
        reopened.recover()
        recovered, first = reopened.reserve_verification_send(
            {
                "id": accepted["id"],
                "request_key": "after-restart",
                "expected_render_hash": accepted["rendered"]["render_hash"],
            }
        )
        assert not first and recovered["delivery_state"] == "unknown"
        assert recovered["rendered"] == accepted["rendered"]
        assert tuple(reopened.db.execute("SELECT * FROM sends").fetchone()) == original_receipt
    finally:
        reopened.close()
