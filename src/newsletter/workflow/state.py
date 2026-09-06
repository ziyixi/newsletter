"""Small durable ledgers shared by DAG nodes and the protected publication tail."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

from newsletter.contracts import canonical_json
from newsletter.store import Store, StoreError, now
from newsletter.types import Payload
from newsletter.usage import UsageRecord, UsageSummary, summarize_usage


class WorkflowState:
    def __init__(self, store: Store) -> None:
        self.store = store
        with store.lock:
            store.db.executescript("""
                CREATE TABLE IF NOT EXISTS model_usage (
                    invocation_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL,
                    body TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS model_usage_scope ON model_usage(scope_id);
                CREATE TABLE IF NOT EXISTS candidate_history (
                    id TEXT PRIMARY KEY, body TEXT NOT NULL,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                    disposition TEXT NOT NULL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workflow_editions (
                    edition_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL,
                    editor_result TEXT NOT NULL, required_packets TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workflow_archives (
                    run_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    packet_id TEXT NOT NULL, error_code TEXT NOT NULL);
            """)

    def usage_sink(self, scope_id: str) -> Callable[[UsageRecord], None]:
        def save(record: UsageRecord) -> None:
            with self.store.transaction():
                previous = self.store.db.execute(
                    "SELECT scope_id FROM model_usage WHERE invocation_id=?", (record["id"],)
                ).fetchone()
                if previous is not None and previous[0] != scope_id:
                    raise StoreError("conflict", "Usage scope cannot change")
                self.store.db.execute(
                    "INSERT INTO model_usage VALUES (?,?,?,?) ON CONFLICT(invocation_id) "
                    "DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at",
                    (record["id"], scope_id, canonical_json(record), now()),
                )

        return save

    def usage(self, scope_id: str) -> UsageSummary:
        with self.store.lock:
            records = self.store.db.execute(
                "SELECT body FROM model_usage WHERE scope_id=? ORDER BY rowid", (scope_id,)
            ).fetchall()
        return summarize_usage([cast(UsageRecord, json.loads(row[0])) for row in records])

    def archive_result(self, run_id: str, *, packet_id: str = "", error_code: str = "") -> None:
        with self.store.transaction():
            self.store.db.execute(
                "INSERT INTO workflow_archives VALUES(?,?,?,?) ON CONFLICT(run_id) "
                "DO UPDATE SET state=excluded.state,packet_id=excluded.packet_id,error_code=excluded.error_code",
                (run_id, "failed" if error_code else "queued", packet_id, error_code),
            )

    def remember(self, candidates: list[Payload], issue_date: str) -> None:
        with self.store.transaction():
            for candidate in candidates:
                self.store.db.execute(
                    "INSERT INTO candidate_history VALUES(?,?,?,?,?,?) ON CONFLICT(id) "
                    "DO UPDATE SET body=excluded.body,last_seen=excluded.last_seen",
                    (
                        candidate["id"],
                        canonical_json(candidate),
                        issue_date,
                        issue_date,
                        "seen",
                        "",
                    ),
                )

    def history(self, issue_date: str, limit: int = 90) -> list[Payload]:
        with self.store.lock:
            rows = self.store.db.execute(
                "SELECT * FROM candidate_history WHERE first_seen<? "
                "ORDER BY last_seen DESC,id LIMIT ?",
                (issue_date, min(limit, 120)),
            ).fetchall()
        return [
            {
                **json.loads(row["body"]),
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "disposition": row["disposition"],
                "selection_reason": row["reason"],
            }
            for row in rows
        ]

    def mark(self, ids: list[str], disposition: str, reason: str = "") -> None:
        if disposition not in {"seen", "researched", "used", "watch"}:
            raise ValueError("Invalid candidate disposition")
        with self.store.transaction():
            self.store.db.executemany(
                "UPDATE candidate_history SET disposition=?,reason=? WHERE id=?",
                [(disposition, reason[:2000], item) for item in ids],
            )

    def bind_edition(
        self, edition_id: str, run_id: str, result: Payload, required_packets: list[str]
    ) -> None:
        encoded = canonical_json(result)
        required = canonical_json(sorted(set(required_packets)))
        with self.store.transaction():
            previous = self.store.db.execute(
                "SELECT run_id,editor_result,required_packets FROM workflow_editions WHERE edition_id=?",
                (edition_id,),
            ).fetchone()
            if previous is not None:
                if tuple(previous) != (run_id, encoded, required):
                    raise StoreError("conflict", "Frozen workflow edition cannot change")
                return
            self.store.db.execute(
                "INSERT INTO workflow_editions VALUES(?,?,?,?)",
                (edition_id, run_id, encoded, required),
            )

    def edition(self, edition_id: str) -> Payload | None:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT * FROM workflow_editions WHERE edition_id=?", (edition_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "result": json.loads(row["editor_result"]),
            "required_packets": json.loads(row["required_packets"]),
        }

    def assert_publishable(self, edition_id: str) -> None:
        binding = self.edition(edition_id)
        if binding is None:
            return
        ids = binding["required_packets"]
        with self.store.lock:
            states = [
                self.store.db.execute(
                    "SELECT projection FROM packets WHERE id=?", (item,)
                ).fetchone()
                for item in ids
            ]
        if not ids or any(row is None or row[0] != "done" for row in states):
            raise StoreError(
                "conflict", "Adopted research must be confirmed in Notion before sending"
            )
