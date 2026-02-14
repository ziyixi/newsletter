"""Fake server — mocks all external APIs for integration testing.

Provides deterministic, canned responses so the newsletter pipeline
can be tested end-to-end without hitting real external services.

Usage:
  python server.py          # starts on port 8080
  FAKE_SERVER_PORT=9090 python server.py
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_FIXTURES = Path(__file__).parent / "fixtures"
_PORT = int(os.getenv("FAKE_SERVER_PORT", "8080"))


def _load_fixture(name: str) -> str:
    """Load a fixture file by name."""
    return (_FIXTURES / name).read_text(encoding="utf-8")


class FakeHandler(BaseHTTPRequestHandler):
    """HTTP handler that returns canned responses for each API endpoint."""

    def do_GET(self) -> None:
        path = self.path.split("?")[0]  # strip query params

        routes: dict[str, tuple[str, str]] = {
            "/v1/forecast": ("weather.json", "application/json"),
            "/v0/topstories.json": ("hn_topstories.json", "application/json"),
            "/v0/item/1.json": ("hn_item_1.json", "application/json"),
            "/v0/item/2.json": ("hn_item_2.json", "application/json"),
            "/v0/item/3.json": ("hn_item_3.json", "application/json"),
            "/v0/item/4.json": ("hn_item_4.json", "application/json"),
            "/v0/item/5.json": ("hn_item_5.json", "application/json"),
            "/trending": ("github_trending.html", "text/html"),
            "/trending/python": ("github_trending.html", "text/html"),
            "/trending/go": ("github_trending.html", "text/html"),
            "/api/recommendation": ("todo.json", "application/json"),
            "/rss/feed": ("rss_feed.xml", "application/xml"),
            "/health": ("", "text/plain"),
        }

        if path in routes:
            fixture, content_type = routes[path]
            body = _load_fixture(fixture) if fixture else "OK"
            self._respond(200, body, content_type)
        else:
            self._respond(404, json.dumps({"error": f"Unknown path: {path}"}), "application/json")

    def _respond(self, code: int, body: str, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        """Minimal logging."""
        print(f"[fake-server] {args[0]}")


def main() -> None:
    server = HTTPServer(("0.0.0.0", _PORT), FakeHandler)
    print(f"🧪  Fake server listening on port {_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
