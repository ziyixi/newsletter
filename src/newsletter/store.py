"""SQLite is the authority. External side effects are never retried implicitly."""

import base64
import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Unpack, cast

from newsletter.contracts import canonical_json, content_hash
from newsletter.types import EditionPatch, EditionRecord, Payload, ProjectionState


class StoreError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path, mode: str, max_pending_jobs: int = 8) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.max_pending_jobs = max_pending_jobs
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS packets (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                principal TEXT NOT NULL, request_key TEXT NOT NULL, digest TEXT NOT NULL,
                body TEXT NOT NULL, projection TEXT NOT NULL DEFAULT 'pending',
                UNIQUE(principal, request_key));
            CREATE TABLE IF NOT EXISTS editions (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, digest TEXT NOT NULL,
                state TEXT NOT NULL, body TEXT NOT NULL, snapshot TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sends (
                issue_date TEXT PRIMARY KEY, edition_id TEXT UNIQUE NOT NULL,
                request_key TEXT UNIQUE NOT NULL, render_hash TEXT NOT NULL);
        """)
        with self.transaction():
            row = self.db.execute("SELECT value FROM metadata WHERE key='mode'").fetchone()
            if row and row[0] != mode:
                raise ValueError("Do not reuse mock storage for live publication")
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('mode', ?)", (mode,))
        self.mode = mode

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def close(self) -> None:
        self.db.close()

    def bind_delivery_target(self, target: dict[str, str]) -> None:
        """A database cannot silently change the audience or delivery provider."""
        digest = content_hash(target)
        with self.transaction():
            row = self.db.execute(
                "SELECT value FROM metadata WHERE key='delivery_target'"
            ).fetchone()
            if row and row[0] != digest:
                raise ValueError("Delivery target changed; use a new data directory")
            self.db.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('delivery_target', ?)", (digest,)
            )

    def save_supplements(self, edition_id: str, packets: list[Payload]) -> None:
        """Only the trusted worker calls this, after validating editor research."""
        with self.transaction():
            row = self.db.execute(
                "SELECT snapshot FROM editions WHERE id=?", (edition_id,)
            ).fetchone()
            snapshot = json.loads(row[0])
            edition = self.get(edition_id)
            for packet in packets:
                if self.db.execute("SELECT 1 FROM packets WHERE id=?", (packet["id"],)).fetchone():
                    raise StoreError("conflict", "Supplemental packet ID is already in use")
                self.db.execute(
                    "INSERT INTO packets(id,principal,request_key,digest,body) VALUES(?,?,?,?,?)",
                    (
                        packet["id"],
                        "editor",
                        edition_id + ":" + packet["id"],
                        content_hash(packet["content"]),
                        canonical_json(packet),
                    ),
                )
                snapshot.append(packet)
                edition["packet_ids"].append(packet["id"])
            self.db.execute(
                "UPDATE editions SET snapshot=? WHERE id=?", (canonical_json(snapshot), edition_id)
            )
            self._write(edition)

    def put_packet(self, request: Payload, principal: str = "producer") -> Payload:
        with self.transaction():
            return self._put_packet(request, principal)

    def _put_packet(self, request: Payload, principal: str) -> Payload:
        """Insert within the caller's transaction; used for atomic collection batches."""
        digest = content_hash(request)
        row = self.db.execute(
            "SELECT digest, body FROM packets WHERE principal=? AND request_key=?",
            (principal, request["request_key"]),
        ).fetchone()
        if row:
            if row["digest"] != digest:
                raise StoreError("conflict", "request_key was used for different material")
            return json.loads(row["body"])
        packet = {
            "id": str(uuid.uuid4()),
            "workflow_id": request["workflow_id"],
            "producer_id": principal,
            "content": request["content"],
            "content_hash": content_hash(request["content"]),
            "created_at": now(),
            "is_fixture": self.mode == "mock",
        }
        self.db.execute(
            "INSERT INTO packets(id,principal,request_key,digest,body) VALUES(?,?,?,?,?)",
            (packet["id"], principal, request["request_key"], digest, canonical_json(packet)),
        )
        return packet

    def read_inbox(self, limit: int = 20, cursor: str = "") -> Payload:
        with self.lock:
            top = self.db.execute("SELECT COALESCE(MAX(seq),0) FROM packets").fetchone()[0]
            before = top + 1
            if cursor:
                try:
                    top, before = json.loads(base64.urlsafe_b64decode(cursor))
                    if any(type(v) is not int or not 0 <= v <= 2**63 - 1 for v in (top, before)):
                        raise ValueError()
                except (ValueError, TypeError, KeyError):
                    raise StoreError("invalid_argument", "Invalid inbox cursor") from None
            rows = self.db.execute(
                "SELECT seq,body FROM packets WHERE seq<=? AND seq<? ORDER BY seq DESC LIMIT ?",
                (top, before, limit + 1),
            ).fetchall()
            selected = rows[:limit]
            next_cursor = ""
            if len(rows) > limit:
                next_cursor = base64.urlsafe_b64encode(
                    json.dumps([top, selected[-1]["seq"]]).encode()
                ).decode()
            return {
                "packets": [json.loads(r["body"]) for r in selected],
                "next_cursor": next_cursor,
            }

    def prepare(self, request: Payload) -> EditionRecord:
        digest = content_hash(request)
        with self.transaction():
            row = self.db.execute(
                "SELECT digest,body FROM editions WHERE request_key=?", (request["request_key"],)
            ).fetchone()
            if row:
                if row["digest"] != digest:
                    raise StoreError("conflict", "request_key was used for another edition")
                return cast(EditionRecord, json.loads(row["body"]))
            if (
                self.db.execute(
                    "SELECT COUNT(*) FROM editions WHERE state IN ('queued','running')"
                ).fetchone()[0]
                >= self.max_pending_jobs
            ):
                raise StoreError("busy", "Editorial queue is full")
            packets = []
            for packet_id in request["packet_ids"]:
                row = self.db.execute(
                    "SELECT body FROM packets WHERE id=?", (packet_id,)
                ).fetchone()
                if not row:
                    raise StoreError("not_found", "One or more packets do not exist")
                packets.append(json.loads(row[0]))
            at = now()
            edition: EditionRecord = {
                "id": str(uuid.uuid4()),
                "issue_date": request["issue_date"],
                "state": "queued",
                "packet_ids": request["packet_ids"],
                "delivery_state": "not_requested",
                "created_at": at,
                "updated_at": at,
                "is_fixture": self.mode == "mock",
            }
            self.db.execute(
                "INSERT INTO editions VALUES (?,?,?,?,?,?)",
                (
                    edition["id"],
                    request["request_key"],
                    digest,
                    "queued",
                    canonical_json(edition),
                    canonical_json(packets),
                ),
            )
            return edition

    def get(self, edition_id: str) -> EditionRecord:
        with self.lock:
            row = self.db.execute("SELECT body FROM editions WHERE id=?", (edition_id,)).fetchone()
            if not row:
                raise StoreError("not_found", "Edition not found")
            # Only this store writes edition records, after boundary validation.
            return cast(EditionRecord, json.loads(row[0]))

    def _write(self, edition: EditionRecord) -> None:
        edition["updated_at"] = now()
        self.db.execute(
            "UPDATE editions SET state=?,body=? WHERE id=?",
            (
                edition["state"],
                canonical_json(edition),
                edition["id"],
            ),
        )

    def claim(self) -> tuple[EditionRecord, list[Payload]] | None:
        with self.transaction():
            row = self.db.execute(
                "SELECT body,snapshot FROM editions WHERE state='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if not row:
                return None
            edition = cast(EditionRecord, json.loads(row["body"]))
            edition["state"] = "running"
            self._write(edition)
            return edition, json.loads(row["snapshot"])

    def finish(self, edition_id: str, **fields: Unpack[EditionPatch]) -> EditionRecord:
        with self.transaction():
            edition = self.get(edition_id)
            edition.update(fields)
            self._write(edition)
            return edition

    def recover(self) -> None:
        """Interrupted research is reported; ambiguous mail is never auto-resubmitted."""
        with self.transaction():
            for row in self.db.execute("SELECT body FROM editions").fetchall():
                edition = cast(EditionRecord, json.loads(row[0]))
                changed = False
                if edition["state"] == "running":
                    edition.update({"state": "failed", "error_code": "interrupted"})
                    changed = True
                if edition["delivery_state"] == "submitting":
                    edition.update({"delivery_state": "unknown", "error_code": "delivery_unknown"})
                    changed = True
                if changed:
                    self._write(edition)
            self.db.execute("UPDATE packets SET projection='unknown' WHERE projection='submitting'")

    def reserve_send(self, request: Payload) -> tuple[EditionRecord, bool]:
        with self.transaction():
            edition = self.get(request["id"])
            if edition["state"] != "ready":
                raise StoreError("conflict", "Only a ready edition can be sent")
            if edition["rendered"]["render_hash"] != request["expected_render_hash"]:
                raise StoreError("conflict", "Approval does not match the frozen preview")
            row = self.db.execute(
                "SELECT * FROM sends WHERE request_key=?", (request["request_key"],)
            ).fetchone()
            if row and (
                row["edition_id"] != request["id"]
                or row["render_hash"] != request["expected_render_hash"]
            ):
                raise StoreError("conflict", "Send request_key was used for a different approval")
            row = self.db.execute(
                "SELECT * FROM sends WHERE issue_date=?", (edition["issue_date"],)
            ).fetchone()
            if row:
                if row["edition_id"] != edition["id"]:
                    raise StoreError("conflict", "This issue already has a delivery attempt")
                return edition, False
            self.db.execute(
                "INSERT INTO sends VALUES(?,?,?,?)",
                (
                    edition["issue_date"],
                    edition["id"],
                    request["request_key"],
                    request["expected_render_hash"],
                ),
            )
            edition["delivery_state"] = "submitting"
            self._write(edition)
            return edition, True

    def claim_projection(self) -> Payload | None:
        with self.transaction():
            row = self.db.execute(
                "SELECT id,body FROM packets WHERE projection='pending' ORDER BY seq LIMIT 1"
            ).fetchone()
            if not row:
                return None
            self.db.execute("UPDATE packets SET projection='submitting' WHERE id=?", (row["id"],))
            return json.loads(row["body"])

    def projection_result(self, packet_id: str, state: ProjectionState) -> None:
        with self.transaction():
            self.db.execute("UPDATE packets SET projection=? WHERE id=?", (state, packet_id))

    def recent_history(self) -> list[EditionRecord]:
        with self.lock:
            rows = self.db.execute(
                "SELECT body FROM editions ORDER BY rowid DESC LIMIT 60"
            ).fetchall()
        return [
            e
            for row in rows
            if (e := cast(EditionRecord, json.loads(row[0])))["delivery_state"]
            in {"provider_accepted", "unknown"}
        ][:7]
