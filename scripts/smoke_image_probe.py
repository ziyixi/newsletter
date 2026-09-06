"""Container-side probe, supplied over stdin by smoke_image.py, never baked into images."""

import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from importlib.metadata import distributions, version
from importlib.resources import files
from pathlib import Path


def check_package(expected: dict[str, str]) -> None:
    from newsletter.preflight import check_proto_dependency

    assert os.getuid() == os.getgid() == 10001
    assert os.statvfs("/").f_flag & os.ST_RDONLY
    assert len(Path("/proc/net/route").read_text().splitlines()) == 1
    for _, name in socket.if_nameindex():
        if name != "lo":
            assert not int(Path("/sys/class/net", name, "flags").read_text(), 16) & 1
    package = files("newsletter")
    assert "site-packages/newsletter" in str(package)
    assert not Path("/opt/newsletter/src").exists()
    for relative, digest in expected.items():
        assert hashlib.sha256(package.joinpath(relative).read_bytes()).hexdigest() == digest, (
            relative
        )
    assert not package.joinpath("generated").exists()
    assert all(
        importlib.util.find_spec(name) is None
        for name in ("pytest", "ruff", "mypy", "build", "uv", "newsletter.generated")
    )
    assert shutil.which("uv") is None
    check_proto_dependency()


def check_http(root: Path) -> None:
    from newsletter.collection.instructions import load_instructions
    from newsletter.contracts import content_hash
    from newsletter.rendering import preview_html

    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    tokens = {role: secrets.token_urlsafe(32) for role in ("INGEST", "EDITOR", "SEND")}
    environment = {
        "PATH": os.defpath,
        "HOME": str(root),
        "TMPDIR": str(root),
        "LANG": "C.UTF-8",
        "NEWSLETTER_MODE": "mock",
        "NEWSLETTER_EDITOR": "mock",
        "NEWSLETTER_MAIL": "fake",
        "NEWSLETTER_ALLOW_SEND": "false",
        "NEWSLETTER_NOTION": "fake",
        "NEWSLETTER_TODOFY": "fake",
        "NEWSLETTER_DATA_DIR": str(root / "data"),
        **{f"NEWSLETTER_{role}_TOKEN": value for role, value in tokens.items()},
    }
    process = subprocess.Popen(
        [sys.executable, "-I", "-m", "newsletter.cli", "serve", "--port", str(port)],
        cwd=root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(path, data=None, *, html=False):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": "Bearer " + tokens["EDITOR"],
                "Content-Type": "application/json",
            },
        )
        with client.open(req, timeout=3) as response:
            if html:
                assert response.status == 200
                assert response.headers["Cache-Control"] == "no-store"
                assert "sandbox" in response.headers["Content-Security-Policy"]
                return response.read().decode()
            return json.load(response)

    def poll(path, predicate):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Image smoke service exited before completion")
            try:
                result = request(path)
                if predicate(result):
                    return result
            except (urllib.error.URLError, TimeoutError):
                pass
            time.sleep(0.05)
        raise TimeoutError("Image loopback HTTP smoke exceeded its deadline")

    try:
        poll("/healthz", lambda value: value["status"] == "ok")
        run = request("/v1/runs", {"request_key": "image-smoke", "issue_date": "2026-09-05"})
        run = poll(
            "/v1/runs/" + run["id"], lambda value: value["state"] in {"ready", "failed", "blocked"}
        )
        assert run["state"] == "ready", run.get("error_code")
        instruction_dir = Path(str(files("newsletter").joinpath("instructions")))
        assert len(run["directions"]) == len(load_instructions(instruction_dir))
        assert all(direction["state"] == "collected" for direction in run["directions"])
        path = "/v1/editions/" + run["edition_id"]
        edition = request(path)
        assert edition["state"] == "ready" and edition["is_fixture"] is True
        assert edition["delivery_state"] == "not_requested" and not edition["provider_message_id"]
        rendered = edition["rendered"]
        assert rendered["render_hash"] == content_hash(
            {key: rendered[key] for key in ("html", "text", "chart_png")}
        )
        preview = request(path + "/preview", html=True)
        assert preview == preview_html(rendered)
        assert "MOCK" in preview and "TODOFY / 与你有关" in preview
        assert not list(root.rglob("*.eml"))
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main(payload: dict) -> None:
    check_package(payload["source_hashes"])
    with tempfile.TemporaryDirectory(prefix="newsletter-image-probe-") as temporary:
        root = Path(temporary)
        startup = root / "startup.py"
        startup.write_text(payload["startup_source"])
        subprocess.run(
            [sys.executable, "-I", str(startup)],
            cwd=root,
            env={"PATH": os.defpath, "HOME": str(root), "TMPDIR": str(root), "LANG": "C.UTF-8"},
            check=True,
            timeout=40,
        )
        check_http(root)
        assert not list(root.rglob("auth.json")) and not list(root.rglob("*.eml"))
    print(
        json.dumps(
            {
                "source_files_exact": len(payload["source_hashes"]),
                "proto_version": version("ziyixi-protos"),
                "production_distributions": len(list(distributions())),
                "real_codex_startups": 2,
                "mock_http": "ready/preview",
                "mail_files": 0,
                "external_network": False,
                "rootfs_read_only": True,
                "uid": os.getuid(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main(json.load(sys.stdin))
