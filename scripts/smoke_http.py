"""Run the installed service on loopback with random in-memory tokens and fake providers.

No existing .env/auth is read. No external service is contacted. All artifacts
are disposable and live below a fresh TemporaryDirectory, never the real DB.
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from importlib.resources import files
from pathlib import Path


def main():
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    with tempfile.TemporaryDirectory(
        prefix="newsletter-http-smoke-"
    ) as temporary:
        env = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "TMPDIR", "LANG")
            if key in os.environ
        }
        tokens = {
            role: secrets.token_urlsafe(32)
            for role in ("INGEST", "EDITOR", "SEND")
        }
        env.update(
            {
                f"NEWSLETTER_{role}_TOKEN": token
                for role, token in tokens.items()
            }
        )
        env.update(
            NEWSLETTER_MODE="mock",
            NEWSLETTER_EDITOR="mock",
            NEWSLETTER_MAIL="fake",
            NEWSLETTER_NOTION="fake",
            NEWSLETTER_TODOFY="fake",
            NEWSLETTER_DATA_DIR=str(Path(temporary) / "data"),
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "newsletter.cli",
                "serve",
                "--port",
                str(port),
            ],
            env=env,
            cwd=temporary,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, data=None, role="EDITOR"):
            encoded = json.dumps(data).encode() if data is not None else None
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=encoded,
                headers={
                    "Authorization": "Bearer " + tokens[role],
                    "Content-Type": "application/json",
                },
            )
            with client.open(req, timeout=3) as response:
                return json.load(response)

        def poll(fn, predicate):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Smoke service exited early")
                try:
                    value = fn()
                    if predicate(value):
                        return value
                except (urllib.error.URLError, TimeoutError):
                    pass
                time.sleep(0.05)
            raise TimeoutError("Loopback smoke did not complete")

        try:
            poll(
                lambda: request("/healthz"),
                lambda value: value["status"] == "ok",
            )
            material = json.loads(
                files("newsletter")
                .joinpath("fixtures/packets.json")
                .read_text()
            )[0]
            packet = request("/v1/packets", material, "INGEST")
            edition = request(
                "/v1/editions",
                {
                    "request_key": "smoke-edition",
                    "issue_date": "2026-09-05",
                    "packet_ids": [packet["id"]],
                },
            )
            path = "/v1/editions/" + edition["id"]
            ready = poll(
                lambda: request(path),
                lambda value: (
                    value["state"] != "queued" and value["state"] != "running"
                ),
            )
            assert ready["state"] == "ready", ready.get("error_code")
            assert ready["personal_digest"]["is_fixture"]
            assert len(ready["personal_digest"]["items"]) == 3
            assert "研究讨论时间待确认" in ready["rendered"]["html"]
            approval = {
                "id": ready["id"],
                "request_key": "smoke-send",
                "expected_render_hash": ready["rendered"]["render_hash"],
            }
            assert (
                request(path + "/send", approval, "SEND")["delivery_state"]
                == "simulated"
            )
            assert (
                request(path + "/send", approval, "SEND")["delivery_state"]
                == "simulated"
            )
            assert (
                len(list((Path(temporary) / "data" / "outbox").glob("*.eml")))
                == 1
            )
            print(
                "Loopback HTTP smoke passed: ingest → background editor → frozen preview → simulated mail (one attempt)."
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


if __name__ == "__main__":
    main()
