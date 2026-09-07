"""Offline startup gates; injected SDK/HTTP never use credentials or providers."""

import asyncio
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest

from newsletter import preflight as startup
from newsletter.codex_runtime import skill_paths
from newsletter.notion_api import SCHEMAS
from newsletter.settings import Settings
from newsletter.store import Store


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        ingest_token="i" * 32,
        editor_token="e" * 32,
        send_token="s" * 32,
    )


@pytest.fixture
def live(settings, tmp_path):
    home = tmp_path / "isolated-auth"
    home.mkdir()
    return replace(settings, mode="live", editor_backend="codex", codex_home=home)


@pytest.fixture
def sdk(monkeypatch, live):
    actual = pytest.importorskip("openai_codex")
    state = SimpleNamespace(
        closed=False,
        requests=[],
        account_type="chatgpt",
        model=live.model,
        skills_enabled=False,
        fail=False,
        hang=False,
        config=None,
    )

    class Client:
        def __init__(self, config):
            state.config = config
            self._client = self

        async def __aenter__(self):
            if state.fail:
                raise RuntimeError("upstream-response-secret")
            if state.hang:
                await asyncio.Event().wait()
            return self

        async def account(self, *, refresh_token=False):
            assert refresh_token is True
            state.requests.append("account/read")
            return SimpleNamespace(
                account=SimpleNamespace(root=SimpleNamespace(type=state.account_type))
            )

        async def request(self, method, params, *, response_model):
            state.requests.append(method)
            if method == "skills/list":
                return response_model.model_validate(
                    {
                        "data": [
                            {
                                "cwd": state.config.cwd,
                                "errors": [],
                                "skills": [
                                    {
                                        "path": path,
                                        "name": Path(path).parent.name,
                                        "scope": "system",
                                        "enabled": state.skills_enabled,
                                        "description": "fixture",
                                    }
                                    for path in sorted(skill_paths(live.codex_home))
                                ],
                            }
                        ]
                    }
                )
            assert method == "model/list"
            assert params["includeHidden"] is True
            if "cursor" not in params:
                return response_model.model_validate({"data": [], "nextCursor": "second-page"})
            assert params["cursor"] == "second-page"
            return SimpleNamespace(data=[SimpleNamespace(model=state.model)], next_cursor=None)

        async def close(self):
            state.closed = True

    module = ModuleType("offline-sdk-fixture")
    module.AsyncCodex = Client
    module.CodexConfig = actual.CodexConfig

    async def host_fixture(host, workspace):
        assert workspace.is_dir()
        state.requests.append("host/help")

    monkeypatch.setattr(startup, "_host_executable", host_fixture)
    monkeypatch.setattr(startup, "_runtime_files", lambda: (Path("codex"), Path("host")))
    return module, state


async def test_mock_checks_storage_real_package_resources_without_provider_calls(settings):
    with pytest.MonkeyPatch.context() as patch:

        def unexpected(*args, **kwargs):
            raise AssertionError("No provider may be selected in mock mode")

        patch.setattr(startup, "load_sdk", unexpected)
        report = await startup.preflight(settings)
    assert report.checks == (
        "model_output_schema_subset",
        "sqlite_wal_write_and_integrity",
        "proto_policy_template_cjk_png",
    )
    assert not report.limitations
    assert list(settings.data_dir.iterdir()) == []


async def test_invalid_writer_schema_stops_startup_before_storage_or_provider_checks(
    settings, monkeypatch
):
    from newsletter import schema_compat
    from newsletter.errors import EditorError
    from newsletter.workflow import story_editor

    real_writer_schema = story_editor.story_writer_schema

    def broken_writer(*args, **kwargs):
        schema = real_writer_schema(*args, **kwargs)
        schema["properties"]["supplemental_packets"]["uniqueItems"] = True
        return schema

    def unexpected(*args, **kwargs):
        raise AssertionError("A bad schema must stop before other startup work")

    monkeypatch.setattr(story_editor, "story_writer_schema", broken_writer)
    monkeypatch.setattr(startup, "_check_storage", unexpected)
    monkeypatch.setattr(startup, "_check_codex", unexpected)
    with pytest.raises(startup.PreflightError) as error:
        await startup.preflight(settings)
    assert error.value.code == "MODEL_SCHEMA_CHECK_FAILED"
    assert not settings.data_dir.exists()
    # The independent catalog gate catches the same future regression offline.
    with pytest.raises(EditorError, match="configuration"):
        schema_compat.check_production_output_schemas()


async def test_existing_database_is_checked_without_changing_records(settings):
    store = Store(settings.data_dir / "newsletter.sqlite3", "mock")
    try:
        before = list(store.db.iterdump())
        await startup.preflight(settings, store=store)
        assert list(store.db.iterdump()) == before
    finally:
        store.close()


async def test_live_checks_managed_auth_disabled_skills_and_paginated_models(live, sdk):
    module, state = sdk
    report = await startup.preflight(live, sdk=module)
    assert state.requests == [
        "host/help",
        "skills/list",
        "account/read",
        "model/list",
        "model/list",
    ]
    assert state.closed
    assert "codex_runtime_host_auth_skills_model_catalog" in report.checks
    assert any("do not execute a model" in item for item in report.limitations)
    assert list(live.data_dir.iterdir()) == []


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("account_type", "apiKey", "CODEX_CHATGPT_AUTH_REQUIRED"),
        ("model", "missing-model", "CODEX_MODEL_UNAVAILABLE"),
        ("skills_enabled", True, "CODEX_CHECK_FAILED"),
        ("fail", True, "CODEX_CHECK_FAILED"),
    ],
)
async def test_codex_startup_failures_are_closed_and_secret_free(live, sdk, field, value, code):
    module, state = sdk
    setattr(state, field, value)
    with pytest.raises(startup.PreflightError) as error:
        await startup.preflight(live, sdk=module)
    assert error.value.code == code
    assert str(error.value) == code
    assert "secret" not in repr(error.value)
    assert state.closed


async def test_codex_timeout_closes_client(live, sdk, monkeypatch):
    module, state = sdk
    state.hang = True
    monkeypatch.setattr(startup, "CODEX_TIMEOUT", 0.01)
    with pytest.raises(startup.PreflightError, match="CODEX_CHECK_FAILED"):
        await startup.preflight(live, sdk=module)
    assert state.closed


async def test_missing_font_is_a_startup_failure(settings, monkeypatch):
    def missing(*args, **kwargs):
        raise ValueError("private-configured-path")

    monkeypatch.setattr(startup, "render_chart_png", missing)
    with pytest.raises(startup.PreflightError, match="RESOURCES_CHECK_FAILED"):
        await startup.preflight(settings)


@pytest.fixture
def providers(live):
    return replace(
        live,
        notion_backend="notion",
        notion_token="synthetic-notion-key",
        notion_data_source_id="12345678-1234-1234-1234-123456789abc",
        todofy_backend="todofy",
        todofy_base_url="https://todofy.example.org",
        todofy_user="synthetic-user",
        todofy_password="synthetic-password",
        mail_backend="resend",
        allow_send=True,
        resend_api_key="synthetic-send-key",
        from_email="Newsletter <sender@example.org>",
        recipient_email="reader@example.org",
    )


def notion_response(settings):
    return {
        "object": "data_source",
        "id": settings.notion_data_source_id,
        "properties": {"Renamed column": {"id": "title", "type": "title", "title": {}}},
    }


@pytest.fixture
def dual_notion(providers):
    return replace(
        providers,
        workflow_backend="dag",
        notion_token="synthetic-notion-key-for-offline-tests",
        notion_data_source_id="must-not-use-legacy-target",
        notion_materials_data_source_id="12345678-1234-1234-1234-123456789abc",
        notion_editions_data_source_id="22345678-1234-1234-1234-123456789abc",
        todofy_backend="disabled",
    )


def dual_notion_response(settings, kind):
    target = (
        settings.notion_editions_data_source_id
        if kind == "material"
        else settings.notion_materials_data_source_id
    )
    properties = {}
    for key, spec in SCHEMAS[kind].items():
        detail = {}
        if spec.type in {"select", "multi_select"}:
            detail = {"options": [{"name": name} for name in spec.options]}
        elif spec.type == "relation":
            detail = {"data_source_id": target, "type": "single_property", "single_property": {}}
        properties[spec.name if key != "title" else "My renamed title"] = {
            "id": "title" if key == "title" else kind + "_" + key,
            "type": spec.type,
            spec.type: detail,
        }
    return {
        "object": "data_source",
        "id": settings.notion_materials_data_source_id
        if kind == "material"
        else settings.notion_editions_data_source_id,
        "properties": properties,
    }


async def test_dual_notion_validates_both_schemas_read_only(dual_notion, sdk):
    module, _ = sdk
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "api.notion.com"
        assert request.headers["authorization"] == "Bearer " + dual_notion.notion_token
        assert request.headers["notion-version"] == "2026-03-11"
        kind = (
            "material"
            if request.url.path.endswith(dual_notion.notion_materials_data_source_id)
            else "edition"
        )
        return httpx.Response(200, json=dual_notion_response(dual_notion, kind))

    report = await startup.preflight(
        dual_notion, sdk=module, http_transport=httpx.MockTransport(handler)
    )
    assert [request.url.path for request in calls] == [
        "/v1/data_sources/" + dual_notion.notion_materials_data_source_id,
        "/v1/data_sources/" + dual_notion.notion_editions_data_source_id,
    ]
    assert "notion_dual_data_sources_and_managed_schema" in report.checks
    assert "notion_data_source_read_and_title_schema" not in report.checks
    assert any("Update content" in item for item in report.limitations)
    assert any("no page or column was created or changed" in item for item in report.limitations)
    assert "synthetic" not in repr(report)


@pytest.mark.parametrize(
    "change,code",
    [
        ("missing", "NOTION_SCHEMA_MISSING"),
        ("type", "NOTION_SCHEMA_INVALID"),
        ("relation", "NOTION_SCHEMA_INVALID"),
        ("wrong-id", "NOTION_SCHEMA_INVALID"),
    ],
)
async def test_dual_notion_missing_or_wrong_schema_never_auto_migrates(dual_notion, change, code):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        kind = (
            "material"
            if request.url.path.endswith(dual_notion.notion_materials_data_source_id)
            else "edition"
        )
        value = dual_notion_response(dual_notion, kind)
        if kind == "edition":
            props = value["properties"]
            if change == "missing":
                del props[SCHEMAS[kind]["overview"].name]
            elif change == "type":
                props[SCHEMAS[kind]["overview"].name]["type"] = "number"
            elif change == "relation":
                props[SCHEMAS[kind]["material_ids"].name]["relation"]["data_source_id"] = (
                    dual_notion.notion_editions_data_source_id
                )
            else:
                value["id"] = dual_notion.notion_materials_data_source_id
        return httpx.Response(200, json=value)

    with pytest.raises(startup.PreflightError, match=code):
        await startup._check_notion(dual_notion, httpx.MockTransport(handler))
    assert len(calls) == 2


@pytest.mark.parametrize("failure", [429, 500, 503, "timeout", "network"])
async def test_dual_notion_transient_failures_degrade_without_legacy_gates(
    dual_notion, sdk, monkeypatch, failure, caplog
):
    module, _ = sdk
    monkeypatch.setattr(startup, "HTTP_TIMEOUT", 0.01)
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if failure == "timeout":
            await asyncio.Event().wait()
        if failure == "network":
            raise httpx.ConnectError("private-provider-detail", request=request)
        return httpx.Response(failure, json={"message": "private-provider-detail"})

    report = await startup.preflight(
        dual_notion, sdk=module, http_transport=httpx.MockTransport(handler)
    )
    assert len(calls) == 1
    assert "notion_temporarily_unavailable" in report.checks
    assert any("without blocking email" in item for item in report.limitations)
    assert "Legacy projection" not in caplog.text
    assert "private-provider-detail" not in repr(report) + caplog.text


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "NOTION_AUTH_FAILED"),
        (403, "NOTION_AUTH_FAILED"),
        (404, "NOTION_UNAVAILABLE"),
        (302, "NOTION_UNAVAILABLE"),
    ],
)
async def test_dual_notion_auth_and_target_failures_stop_startup(dual_notion, sdk, status, code):
    module, _ = sdk
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"message": "upstream-private-secret"},
            headers={"Location": "https://elsewhere.example.org"},
        )

    with pytest.raises(startup.PreflightError, match=code) as error:
        await startup.preflight(
            dual_notion, sdk=module, http_transport=httpx.MockTransport(handler)
        )
    assert len(calls) == 1
    assert "private" not in repr(error.value)


@pytest.mark.parametrize("failure", ["oversize", "invalid-json", "wrong-content-type"])
async def test_dual_notion_invalid_response_is_a_hard_failure(dual_notion, monkeypatch, failure):
    from newsletter import notion_api

    monkeypatch.setattr(notion_api, "MAX_RESPONSE_BYTES", 64)

    def handler(request):
        assert request.method == "GET"
        if failure == "oversize":
            return httpx.Response(200, json={"private": "x" * 100})
        if failure == "invalid-json":
            return httpx.Response(
                200, content="upstream-private-body", headers={"Content-Type": "application/json"}
            )
        return httpx.Response(200, content="{}", headers={"Content-Type": "text/html"})

    with pytest.raises(startup.PreflightError, match="NOTION_INVALID_RESPONSE") as error:
        await startup._check_notion(dual_notion, httpx.MockTransport(handler))
    assert "private" not in repr(error.value)


async def test_provider_probes_only_get_schema_and_public_health(providers, sdk):
    module, _ = sdk
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        if request.url.host == "api.notion.com":
            assert request.url.path == "/v1/data_sources/" + providers.notion_data_source_id
            assert request.headers["notion-version"] == "2026-03-11"
            assert request.headers["authorization"] == "Bearer " + providers.notion_token
            return httpx.Response(200, json=notion_response(providers))
        assert request.url.host == "todofy.example.org" and request.url.path == "/health"
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"service": "todofy", "status": "healthy"})

    report = await startup.preflight(
        providers, sdk=module, http_transport=httpx.MockTransport(handler)
    )
    assert len(requests) == 2
    assert "resend_configuration_only" in report.checks
    assert any("Insert content" in item for item in report.limitations)
    assert any("Basic Auth" in item for item in report.limitations)
    assert any("No email was sent" in item for item in report.limitations)
    assert "synthetic" not in repr(report)


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (401, {"message": "upstream-secret"}, "NOTION_AUTH_FAILED"),
        (403, {"message": "upstream-secret"}, "NOTION_AUTH_FAILED"),
        (404, {}, "NOTION_UNAVAILABLE"),
        (302, {}, "NOTION_UNAVAILABLE"),
        (200, {"object": "page"}, "NOTION_SCHEMA_INVALID"),
        (200, [], "NOTION_INVALID_RESPONSE"),
    ],
)
async def test_notion_refuses_auth_redirect_and_wrong_schema(providers, sdk, status, body, code):
    module, _ = sdk
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json=body, headers={"Location": "https://elsewhere.example.org"}
        )

    with pytest.raises(startup.PreflightError) as error:
        await startup.preflight(providers, sdk=module, http_transport=httpx.MockTransport(handler))
    assert error.value.code == code
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["wrong-id", "missing-title", "trashed"])
async def test_notion_requires_exact_target_and_title_schema(providers, sdk, change):
    module, _ = sdk
    value = notion_response(providers)
    if change == "wrong-id":
        value["id"] = "11111111-1234-1234-1234-123456789abc"
    elif change == "missing-title":
        value["properties"] = {}
    else:
        value["in_trash"] = True
    with pytest.raises(startup.PreflightError, match="NOTION_SCHEMA_INVALID"):
        await startup.preflight(
            providers,
            sdk=module,
            http_transport=httpx.MockTransport(lambda _: httpx.Response(200, json=value)),
        )


async def test_todofy_health_failure_does_not_try_generating_endpoint(providers, sdk):
    module, _ = sdk
    settings = replace(providers, notion_backend="disabled")
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path == "/health"
        return httpx.Response(200, json={"service": "todofy", "status": "unhealthy"})

    with pytest.raises(startup.PreflightError, match="TODOFY_UNHEALTHY"):
        await startup.preflight(settings, sdk=module, http_transport=httpx.MockTransport(handler))
    assert len(requests) == 1


async def test_mail_header_injection_fails_before_any_email_request(providers, sdk):
    module, _ = sdk
    settings = replace(
        providers,
        notion_backend="disabled",
        todofy_backend="disabled",
        from_email="sender@example.org\r\nBcc: other@example.org",
    )
    with pytest.raises(startup.PreflightError, match="MAIL_CHECK_FAILED"):
        await startup.preflight(settings, sdk=module)


def test_installed_pinned_runtime_and_companion_match_record():
    pytest.importorskip("codex_cli_bin")
    executable, host = startup._runtime_files()
    assert executable.parent == host.parent
    assert host.name == "codex-code-mode-host"


def test_runtime_version_mismatch_fails_closed(monkeypatch):
    pytest.importorskip("codex_cli_bin")
    monkeypatch.setattr(startup, "version", lambda _: "0.0.0")
    with pytest.raises(startup.PreflightError, match="CODEX_VERSION_MISMATCH"):
        startup._runtime_files()


@pytest.mark.parametrize("failure", ["oversize", "invalid-json", "wrong-content-type"])
async def test_provider_response_limits_and_timeout_are_safe(providers, sdk, monkeypatch, failure):
    module, _ = sdk
    monkeypatch.setattr(startup, "MAX_RESPONSE_BYTES", 64)
    monkeypatch.setattr(startup, "HTTP_TIMEOUT", 0.01)

    async def handler(request):
        if failure == "oversize":
            return httpx.Response(200, json={"secret": "x" * 100})
        if failure == "invalid-json":
            return httpx.Response(
                200, content="not-json-private-body", headers={"Content-Type": "application/json"}
            )
        return httpx.Response(200, text="private-error-html")

    with pytest.raises(startup.PreflightError) as error:
        await startup.preflight(providers, sdk=module, http_transport=httpx.MockTransport(handler))
    assert error.value.code == "NOTION_INVALID_RESPONSE"
    assert "private" not in str(error.value)


@pytest.mark.parametrize("provider", ["notion", "todofy"])
@pytest.mark.parametrize("failure", [429, 500, 503, "timeout", "network"])
async def test_optional_provider_transient_failure_is_degraded_not_a_startup_block(
    providers, sdk, monkeypatch, provider, failure, caplog
):
    module, _ = sdk
    settings = replace(
        providers, **{"todofy_backend" if provider == "notion" else "notion_backend": "disabled"}
    )
    monkeypatch.setattr(startup, "HTTP_TIMEOUT", 0.01)
    calls = []

    async def handler(request):
        calls.append(request)
        if failure == "timeout":
            await asyncio.Event().wait()
        if failure == "network":
            raise httpx.ConnectError("private-provider-detail", request=request)
        return httpx.Response(failure, json={"message": "private-provider-detail"})

    report = await startup.preflight(
        settings, sdk=module, http_transport=httpx.MockTransport(handler)
    )
    assert len(calls) == 1
    assert provider + "_temporarily_unavailable" in report.checks
    assert "private" not in repr(report)
    assert "private" not in caplog.text
    assert "startup check degraded" in caplog.text
    assert "resend_configuration_only" in report.checks


@pytest.mark.parametrize("status", [401, 403, 404, 302])
async def test_todofy_auth_or_target_errors_remain_hard_failures(providers, sdk, status):
    module, _ = sdk
    settings = replace(providers, notion_backend="disabled")
    with pytest.raises(startup.PreflightError):
        await startup.preflight(
            settings,
            sdk=module,
            http_transport=httpx.MockTransport(lambda _: httpx.Response(status)),
        )


async def test_modified_proto_fails_before_any_provider(settings, monkeypatch):
    monkeypatch.setattr(startup.pb, "DESCRIPTOR", SimpleNamespace(serialized_pb=b"modified-proto"))
    with pytest.raises(startup.PreflightError, match="PROTO_INTEGRITY_FAILED"):
        await startup.preflight(settings)


async def test_dependency_version_drift_fails_before_any_provider(settings, monkeypatch):
    monkeypatch.setattr(startup, "version", lambda _: "0.0.0")
    with pytest.raises(startup.PreflightError, match="DEPENDENCY_VERSION_MISMATCH"):
        await startup.preflight(settings)


async def test_font_with_only_missing_glyph_boxes_is_rejected(settings, monkeypatch):
    monkeypatch.setattr(
        startup, "load_font", lambda _: SimpleNamespace(getmask=lambda _: b"same-box")
    )
    with pytest.raises(startup.PreflightError, match="CJK_FONT_UNAVAILABLE"):
        await startup.preflight(settings)


def test_nonexecutable_runtime_fails_closed(monkeypatch):
    pytest.importorskip("codex_cli_bin")
    monkeypatch.setattr(startup.os, "access", lambda *_: False)
    with pytest.raises(startup.PreflightError, match="CODEX_EXECUTABLE_UNAVAILABLE"):
        startup._runtime_files()
