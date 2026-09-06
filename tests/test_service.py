import asyncio
import base64
import json
from dataclasses import replace
from importlib.resources import files

import pytest
from fastapi.testclient import TestClient

from newsletter.app import create_app
from newsletter.cli import demo
from newsletter.editor import EditorError, EditorResult, MockEditor
from newsletter.settings import Settings
from newsletter.store import Store, StoreError


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        ingest_token="i" * 32,
        editor_token="e" * 32,
        send_token="s" * 32,
    )


@pytest.fixture
def packet_request():
    return json.loads(files("newsletter").joinpath("fixtures/packets.json").read_text())[0]


def headers(role="editor"):
    return {"Authorization": "Bearer " + {"editor": "e", "ingest": "i", "send": "s"}[role] * 32}


def create_issue(client, request, key="issue1"):
    packet = client.post("/v1/packets", json=request, headers=headers("ingest")).json()
    response = client.post(
        "/v1/editions",
        json={"request_key": key, "issue_date": "2026-09-05", "packet_ids": [packet["id"]]},
        headers=headers(),
    )
    assert response.status_code == 202, response.text
    return response.json()


def run_worker(client):
    client.portal.call(client.app.state.worker.step)


def send_request(edition, key="send1"):
    return {
        "id": edition["id"],
        "request_key": key,
        "expected_render_hash": edition["rendered"]["render_hash"],
    }


def test_http_full_flow_and_simulation(settings, packet_request):
    with TestClient(create_app(settings, start_worker=False)) as client:
        assert client.get("/healthz").status_code == 200
        assert client.post("/v1/inbox/query", json={}).status_code == 401
        assert client.post("/v1/inbox/query", json={}, headers=headers("ingest")).status_code == 401
        edition = create_issue(client, packet_request)
        assert edition["state"] == "queued"
        run_worker(client)
        edition = client.get(f"/v1/editions/{edition['id']}", headers=headers()).json()
        assert edition["state"] == "ready", edition
        assert edition["is_fixture"] is True
        preview = client.get(f"/v1/editions/{edition['id']}/preview", headers=headers())
        assert preview.status_code == 200
        assert "MOCK" in preview.text
        assert preview.headers["Cache-Control"] == "no-store"
        assert not list(settings.data_dir.glob("outbox/*.eml"))
        url = f"/v1/editions/{edition['id']}/send"
        request = send_request(edition)
        assert client.post(url, json=request, headers=headers()).status_code == 401
        wrong = {**request, "expected_render_hash": "0" * 64}
        assert client.post(url, json=wrong, headers=headers("send")).status_code == 409
        sent = client.post(url, json=request, headers=headers("send")).json()
        assert sent["delivery_state"] == "simulated"
        assert client.post(url, json=request, headers=headers("send")).json() == sent
        assert len(list(settings.data_dir.glob("outbox/*.eml"))) == 1


def test_ingress_strictness_and_idempotency(settings, packet_request):
    with TestClient(create_app(settings, start_worker=False)) as client:
        response = client.post("/v1/packets", json=packet_request, headers=headers("ingest"))
        assert response.status_code == 200
        assert (
            client.post("/v1/packets", json=packet_request, headers=headers("ingest")).json()
            == response.json()
        )
        changed = {**packet_request, "workflow_id": "changed"}
        assert (
            client.post("/v1/packets", json=changed, headers=headers("ingest")).status_code == 409
        )
        unknown = {**packet_request, "producer_id": "admin"}
        assert (
            client.post("/v1/packets", json=unknown, headers=headers("ingest")).status_code == 400
        )
        assert (
            client.post(
                "/v1/packets",
                content='{"request_key":"a","request_key":"b"}',
                headers={**headers("ingest"), "Content-Type": "application/json"},
            ).status_code
            == 400
        )
        assert (
            client.post("/v1/packets", content="{}", headers=headers("ingest")).status_code == 415
        )
        assert (
            client.post(
                "/v1/packets",
                content="x" * (settings.max_body_bytes + 1),
                headers={**headers("ingest"), "Content-Type": "application/json"},
            ).status_code
            == 413
        )


def test_inbox_pagination_is_pinned(settings, packet_request):
    store = Store(settings.data_dir / "db", "mock")
    try:
        ids = [store.put_packet({**packet_request, "request_key": str(i)})["id"] for i in range(4)]
        page1 = store.read_inbox(2)
        new = store.put_packet({**packet_request, "request_key": "late"})
        page2 = store.read_inbox(2, page1["next_cursor"])
        assert [p["id"] for p in page1["packets"] + page2["packets"]] == ids[::-1]
        assert new["id"] not in ids
        with pytest.raises(StoreError):
            store.read_inbox(2, "bad-cursor")
        for bad in ([2**64, 0], [False, 1], [-1, 3]):
            with pytest.raises(StoreError):
                store.read_inbox(2, base64.urlsafe_b64encode(json.dumps(bad).encode()).decode())
    finally:
        store.close()


def test_crash_recovery_and_no_repeat_send(settings, packet_request):
    class UncertainMail:
        calls = 0

        async def send(self, edition, idempotency_key):
            self.calls += 1
            raise TimeoutError("vendor secret must not leak")

    mail = UncertainMail()
    with TestClient(create_app(settings, mail=mail, start_worker=False)) as client:
        edition = create_issue(client, packet_request)
        run_worker(client)
        edition = client.app.state.store.get(edition["id"])
        request = send_request(edition)
        response = client.post(
            f"/v1/editions/{edition['id']}/send", json=request, headers=headers("send")
        )
        assert response.json()["delivery_state"] == "unknown"
        assert "vendor secret" not in response.text
        second = create_issue(client, {**packet_request, "request_key": "other"}, "issue2")
        # Simulate an interrupted editor claim before shutdown.
        client.app.state.store.claim()
    with TestClient(create_app(settings, mail=mail, start_worker=False)) as client:
        assert client.app.state.store.get(second["id"])["error_code"] == "interrupted"
        response = client.post(
            f"/v1/editions/{edition['id']}/send", json=request, headers=headers("send")
        )
        assert response.json()["delivery_state"] == "unknown"
        assert mail.calls == 1


def test_one_process_and_immutable_target(settings):
    with TestClient(create_app(settings, start_worker=False)):
        with pytest.raises(RuntimeError, match="Only one service"):
            with TestClient(create_app(settings, start_worker=False)):
                pass
    with pytest.raises(ValueError, match="Delivery target changed"):
        with TestClient(
            create_app(
                replace(settings, recipient_email="different@example.org"), start_worker=False
            )
        ):
            pass


@pytest.mark.parametrize("backend", ["codex", "resend", "notion"])
def test_mock_never_enables_real_adapters(settings, backend):
    changes = {
        "codex": {"editor_backend": "codex"},
        "resend": {"mail_backend": "resend"},
        "notion": {"notion_backend": "notion"},
    }[backend]
    with pytest.raises(ValueError, match="Mock mode forbids"):
        create_app(replace(settings, **changes))


def test_queue_bound_and_prepare_idempotency(settings, packet_request):
    with TestClient(
        create_app(replace(settings, max_pending_jobs=1), start_worker=False)
    ) as client:
        edition = create_issue(client, packet_request)
        assert create_issue(client, packet_request)["id"] == edition["id"]
        response = client.post(
            "/v1/editions",
            json={
                "request_key": "new",
                "issue_date": "2026-09-05",
                "packet_ids": edition["packet_ids"],
            },
            headers=headers(),
        )
        assert response.status_code == 429


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), 0, -1, 3601])
def test_unbounded_timeouts_rejected(settings, timeout):
    with pytest.raises(ValueError, match="Job timeout"):
        replace(settings, job_timeout_seconds=timeout).validate()


def test_data_directory_is_dedicated(settings):
    from pathlib import Path

    for directory in [Path.cwd(), Path.home(), Path("/")]:
        with pytest.raises(ValueError, match="dedicated child"):
            replace(settings, data_dir=directory).validate()


def test_system_style_parent_symlink_uses_canonical_workspace(settings, packet_request, tmp_path):
    real = tmp_path / "real-parent"
    real.mkdir()
    alias = tmp_path / "alias-parent"
    alias.symlink_to(real, target_is_directory=True)
    configured = replace(settings, data_dir=alias / "data")
    with TestClient(create_app(configured, start_worker=False)) as client:
        edition = create_issue(client, packet_request)
        run_worker(client)
        assert client.app.state.store.get(edition["id"])["state"] == "ready"


def test_preview_only_replaces_image_source():
    from newsletter.app import preview_html

    value = {
        "html": '<p>cid:newsletter-chart</p><img src="cid:newsletter-chart">',
        "chart_png": "abc",
    }
    assert preview_html(value) == '<p>cid:newsletter-chart</p><img src="data:image/png;base64,abc">'


@pytest.mark.asyncio
async def test_demo_is_offline_and_exclusive(tmp_path):
    path = await demo(tmp_path / "sample")
    assert path.is_file() and "MOCK" in path.read_text()
    assert len(list((path.parent / "outbox").glob("*.eml"))) == 1
    assert json.loads((path.parent / "edition.json").read_text())["delivery_state"] == "simulated"
    with pytest.raises(FileExistsError):
        await demo(path.parent)


@pytest.mark.parametrize(
    "behavior,expected",
    [
        ("auth", "authentication"),
        ("timeout", "editor_timeout"),
        ("invalid", "editor_invalid_result"),
        ("review", "editorial_review_failed"),
    ],
)
def test_failed_editor_cannot_publish(settings, packet_request, behavior, expected):
    class ProblemEditor:
        async def prepare(self, packets, issue_date, workspace):
            if behavior == "auth":
                raise EditorError("authentication")
            if behavior == "timeout":
                await asyncio.sleep(2)
            result = await MockEditor().prepare(packets, issue_date, workspace)
            if behavior == "invalid":
                result.draft["sections"][0]["paragraphs"][0]["citations"] = ["made-up/source"]
            return EditorResult(
                result.draft, {"passed": False, "findings": ["Insufficient evidence"]}
            )

    with TestClient(
        create_app(
            replace(settings, job_timeout_seconds=0.1), editor=ProblemEditor(), start_worker=False
        )
    ) as client:
        edition = create_issue(client, packet_request)
        run_worker(client)
        final = client.app.state.store.get(edition["id"])
        assert final["error_code"] == expected
        assert final["state"] in {"failed", "blocked"}
        request = {"id": final["id"], "request_key": "attempt", "expected_render_hash": "0" * 64}
        assert (
            client.post(
                f"/v1/editions/{final['id']}/send", json=request, headers=headers("send")
            ).status_code
            == 409
        )
