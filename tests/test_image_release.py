"""Offline image-publication boundaries: fake Docker, synthetic files, no containers."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMAGE_ID = "sha256:" + "a" * 64


@pytest.fixture
def smoke():
    spec = importlib.util.spec_from_file_location(
        "offline_image_smoke", ROOT / "scripts/smoke_image.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source_root(tmp_path):
    package = tmp_path / "src/newsletter"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('"""Synthetic source."""\n')
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "smoke_codex_startup.py").write_text("# Synthetic startup fixture\n")
    (scripts / "smoke_image_probe.py").write_text("# Synthetic container fixture\n")
    return tmp_path


@pytest.fixture
def docker(smoke, monkeypatch):
    state = SimpleNamespace(
        calls=[],
        failure=None,
        metadata={"id": IMAGE_ID, "os": "linux", "architecture": "amd64", "user": "newsletter"},
    )

    def run(command, **kwargs):
        state.calls.append((command, kwargs))
        if command[1:3] == ["image", "inspect"]:
            return SimpleNamespace(stdout=json.dumps(state.metadata))
        if command[1] == "run" and state.failure:
            raise state.failure
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(smoke.subprocess, "run", run)
    return state


def test_smoke_uses_fixed_inspected_id_without_mounts_network_or_credentials(
    smoke, source_root, docker
):
    assert smoke.verify("mutable:tag", "linux/amd64", root=source_root) == IMAGE_ID
    inspect, run, cleanup = docker.calls
    assert inspect[0][-2:] == ["--", "mutable:tag"]
    command, options = run
    for option, value in (
        ("--platform", "linux/amd64"),
        ("--network", "none"),
        ("--pull", "never"),
        ("--user", "10001:10001"),
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges:true"),
    ):
        assert command[command.index(option) + 1] == value
    assert "--read-only" in command and "--rm" in command
    assert not {"--mount", "--volume", "-v", "--env", "--env-file", "-e"} & set(command)
    assert IMAGE_ID in command and "mutable:tag" not in command
    assert options["timeout"] == 120 and options["check"] is True
    assert set(json.loads(options["input"])) == {"source_hashes", "startup_source"}
    name = command[command.index("--name") + 1]
    assert name.startswith("newsletter-image-smoke-")
    assert cleanup[0] == ["docker", "rm", "--force", name]
    assert cleanup[1]["timeout"] == 15
    assert all(call[0][1] not in {"build", "pull", "push", "login"} for call in docker.calls)


@pytest.mark.parametrize(
    "field,value",
    [
        ("architecture", "arm64"),
        ("os", "windows"),
        ("id", "mutable:tag"),
        ("user", ""),
        ("user", "root"),
        ("user", "0:0"),
    ],
)
def test_wrong_image_metadata_is_rejected_before_container_start(
    smoke, source_root, docker, field, value
):
    docker.metadata[field] = value
    with pytest.raises(ValueError):
        smoke.verify("fixture", "linux/amd64", root=source_root)
    assert len(docker.calls) == 1


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired("docker", 120), subprocess.CalledProcessError(1, "docker")],
)
def test_failed_probe_still_removes_only_its_unique_container(smoke, source_root, docker, failure):
    docker.failure = failure
    with pytest.raises(type(failure)):
        smoke.verify("fixture", "linux/amd64", root=source_root)
    name = docker.calls[1][0][docker.calls[1][0].index("--name") + 1]
    assert docker.calls[-1][0] == ["docker", "rm", "--force", name]


@pytest.mark.parametrize(
    "name",
    [
        ".env.production",
        "auth.json",
        "AUTH.JSON",
        "credentials.json",
        "account.key",
        "history.sqlite3",
        "preview.eml",
    ],
)
def test_source_audit_rejects_private_names_without_reading_contents(
    smoke, source_root, name, monkeypatch
):
    path = source_root / "src/newsletter" / name
    path.write_text("Synthetic; contents must never be inspected")
    original = Path.read_bytes

    def read_bytes(candidate):
        assert candidate != path
        return original(candidate)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    with pytest.raises(ValueError, match="private-file"):
        smoke.source_hashes(source_root)


def test_source_audit_rejects_symlinks(smoke, source_root):
    package = source_root / "src/newsletter"
    (package / "alias.py").symlink_to(package / "__init__.py")
    with pytest.raises(ValueError, match="symlinks"):
        smoke.source_hashes(source_root)


def test_source_audit_hashes_package_inputs_but_ignores_bytecode(smoke, source_root):
    package = source_root / "src/newsletter"
    (package / "fixture.json").write_text('{"synthetic":true}')
    (package / "__pycache__").mkdir()
    (package / "__pycache__/cache.pyc").write_bytes(b"synthetic")
    assert set(smoke.source_hashes(source_root)) == {"__init__.py", "fixture.json"}


def test_ci_builds_native_amd64_then_smokes_before_login_and_push_without_rebuild():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    image = ci.split("\n  image:", 1)[1]
    assert "runs-on: ubuntu-24.04" in image and "needs: test" in image
    assert 'test "$(uname -m)" = x86_64' in image
    assert image.index("--audit-source") < image.index("docker build --platform linux/amd64")
    assert image.index("docker build") < image.index("scripts/smoke_image.py --image")
    assert image.index("scripts/smoke_image.py --image") < image.index("docker/login-action")
    assert image.index("docker/login-action") < image.index("docker push")
    assert image.count("docker build ") == 1 and "docker/build-push-action" not in image
    assert 'docker tag "$TESTED_IMAGE"' in image
    assert "service-${GITHUB_SHA}" in image and ' = "$TESTED_IMAGE"' in image
    assert image.count("if: github.ref == 'refs/heads/main' && github.event_name == 'push'") == 2


def test_daily_workflow_never_schedules_or_sends():
    workflow = (ROOT / ".github/workflows/daily.yml").read_text()
    assert "schedule:" not in workflow and "cron:" not in workflow
    assert "workflow_dispatch:" in workflow and "repository_dispatch:" in workflow
    assert "NEWSLETTER_EDITOR_TOKEN" in workflow
    assert all(
        value not in workflow
        for value in ("NEWSLETTER_SEND_TOKEN", "RESEND_API_KEY", "latest send", "/send")
    )


def test_git_ignore_protects_variants_but_keeps_blank_templates():
    ignored = [
        ".env",
        ".env.local",
        ".env.production",
        ".env.backup",
        "auth.json",
        "credentials.json",
        "nested/.env.live",
        "nested/auth.json",
        "account.key",
        "history.sqlite3",
        "preview.eml",
    ]
    allowed = [".env.example", ".env.production.example", "nested/.env.example"]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input="\n".join(ignored + allowed) + "\n",
        text=True,
        capture_output=True,
        check=True,
        env={
            "PATH": os.defpath,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
        timeout=10,
    )
    assert set(result.stdout.splitlines()) == set(ignored)


def test_docker_secret_rules_follow_source_reinclusion(smoke):
    rules = (ROOT / ".dockerignore").read_text().splitlines()
    source_allow = rules.index("!src/newsletter/**")
    for pattern in smoke.PRIVATE_NAMES:
        rule = "**/" + pattern
        if pattern in {".codex-auth", "codex-auth"}:
            rule += "/"
        assert rules.index(rule) > source_allow
