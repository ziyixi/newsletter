"""
Fetch recommended todo tasks from the daily.ziyixi.science API.

Uses HTTP Basic Auth with credentials from environment variables.
Retries once on failure; returns an empty list if both attempts fail
(so the section is simply omitted from the newsletter).
"""

from __future__ import annotations

import os
import time

import requests

from ..config import cfg


def fetch_todo_tasks() -> list[dict]:
    """Fetch top recommended tasks. Returns [] on failure (section skipped)."""
    base = os.environ.get("TODO_API_BASE", "https://daily.ziyixi.science")
    url = f"{base}/api/recommendation"
    params = {"top": 5}
    auth = (cfg.todo_api_user, cfg.todo_api_password)

    if not cfg.todo_api_user or not cfg.todo_api_password:
        print("    ⚠️  TODO_API_USER / TODO_API_PASSWORD not set — skipping")
        return []

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, params=params, auth=auth, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            tasks = data.get("tasks", [])
            return [
                {
                    "rank": t.get("rank", i + 1),
                    "title": t.get("title", ""),
                    "reason": t.get("reason", ""),
                }
                for i, t in enumerate(tasks)
            ]
        except Exception as e:
            print(f"    ⚠️  Todo fetch attempt {attempt}/{max_attempts} failed: {e}")
            if attempt < max_attempts:
                time.sleep(2)

    # All attempts failed — return empty so the section is not rendered
    return []
