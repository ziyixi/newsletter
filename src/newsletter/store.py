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

from newsletter.contracts import canonical_json, content_hash, validate_draft
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
            CREATE TABLE IF NOT EXISTS verification_sends (
                issue_date TEXT PRIMARY KEY, edition_id TEXT UNIQUE NOT NULL,
                request_key TEXT UNIQUE NOT NULL, render_hash TEXT NOT NULL,
                previous_edition_id TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS workflow_editions (
                edition_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL,
                editor_result TEXT NOT NULL, required_packets TEXT NOT NULL,
                projection_required INTEGER NOT NULL DEFAULT 1);
        """)
        with self.transaction():
            columns = {
                row["name"] for row in self.db.execute("PRAGMA table_info(workflow_editions)")
            }
            if "projection_required" not in columns:
                self.db.execute(
                    "ALTER TABLE workflow_editions ADD COLUMN "
                    "projection_required INTEGER NOT NULL DEFAULT 1"
                )
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

    def save_workflow_supplements(self, run_id: str, packets: list[Payload]) -> None:
        """Preserve validated editor citation IDs before the DAG artifact is finalized."""
        with self.transaction():
            for packet in packets:
                previous = self.db.execute(
                    "SELECT body FROM packets WHERE id=?", (packet["id"],)
                ).fetchone()
                body = canonical_json(packet)
                if previous is not None:
                    if previous[0] != body:
                        raise StoreError("conflict", "Research packet identity cannot change")
                    continue
                self.db.execute(
                    "INSERT INTO packets(id,principal,request_key,digest,body) VALUES(?,?,?,?,?)",
                    (
                        packet["id"],
                        "workflow-editor",
                        run_id + ":" + packet["id"],
                        content_hash(packet["content"]),
                        body,
                    ),
                )

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

    def prepare(
        self, request: Payload, *, workflow_binding: Payload | None = None
    ) -> EditionRecord:
        digest = content_hash(request)
        if (
            workflow_binding is not None
            and type(workflow_binding.get("projection_required", True)) is not bool
        ):
            raise StoreError("invalid_argument", "Projection policy must be an explicit boolean")
        with self.transaction():
            row = self.db.execute(
                "SELECT digest,body FROM editions WHERE request_key=?", (request["request_key"],)
            ).fetchone()
            if row:
                if row["digest"] != digest:
                    raise StoreError("conflict", "request_key was used for another edition")
                existing = cast(EditionRecord, json.loads(row["body"]))
                if workflow_binding is not None:
                    binding = self.db.execute(
                        "SELECT run_id,editor_result,required_packets,projection_required "
                        "FROM workflow_editions WHERE edition_id=?",
                        (existing["id"],),
                    ).fetchone()
                    expected = (
                        workflow_binding["run_id"],
                        canonical_json(workflow_binding["result"]),
                        canonical_json(sorted(set(workflow_binding["required_packets"]))),
                        int(workflow_binding.get("projection_required", True)),
                    )
                    if binding is None or tuple(binding) != expected:
                        raise StoreError("conflict", "Frozen workflow edition cannot change")
                return existing
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
            if workflow_binding is not None:
                self.db.execute(
                    "INSERT INTO workflow_editions "
                    "(edition_id,run_id,editor_result,required_packets,projection_required) "
                    "VALUES(?,?,?,?,?)",
                    (
                        edition["id"],
                        workflow_binding["run_id"],
                        canonical_json(workflow_binding["result"]),
                        canonical_json(sorted(set(workflow_binding["required_packets"]))),
                        int(workflow_binding.get("projection_required", True)),
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
            for row in self.db.execute("SELECT body,snapshot FROM editions").fetchall():
                edition = cast(EditionRecord, json.loads(row["body"]))
                changed = False
                if edition["state"] == "running":
                    if self._recoverable_local_render(edition, row["snapshot"]):
                        edition.update({"state": "queued", "error_code": ""})
                    else:
                        edition.update({"state": "failed", "error_code": "interrupted"})
                    changed = True
                if edition["delivery_state"] == "submitting":
                    edition.update({"delivery_state": "unknown", "error_code": "delivery_unknown"})
                    changed = True
                if changed:
                    self._write(edition)
            self.db.execute("UPDATE packets SET projection='unknown' WHERE projection='submitting'")

    def interrupt_preparation(self, edition_id: str) -> None:
        """Graceful cancellation uses the same narrow local-only recovery policy.

        Never retry an editor call, an arbitrary failed edition, a frozen render
        or a delivery attempt. Only assembling an already approved publication
        may be requeued without another model decision.
        """
        with self.transaction():
            row = self.db.execute(
                "SELECT body,snapshot FROM editions WHERE id=?", (edition_id,)
            ).fetchone()
            if row is None:
                return
            edition = cast(EditionRecord, json.loads(row["body"]))
            if edition["state"] != "running":
                return
            if self._recoverable_local_render(edition, row["snapshot"]):
                edition.update({"state": "queued", "error_code": ""})
            else:
                edition.update({"state": "failed", "error_code": "interrupted"})
            self._write(edition)

    def _recoverable_local_render(self, edition: EditionRecord, snapshot_json: str) -> bool:
        """Read-only checks inside the caller's transaction, fail closed on drift."""
        if (
            edition["delivery_state"] != "not_requested"
            or "rendered" in edition
            or self.db.execute(
                "SELECT 1 FROM sends WHERE edition_id=? OR issue_date=?",
                (edition["id"], edition["issue_date"]),
            ).fetchone()
        ):
            return False
        binding = self.db.execute(
            "SELECT run_id,editor_result,required_packets FROM workflow_editions "
            "WHERE edition_id=? AND projection_required=0",
            (edition["id"],),
        ).fetchone()
        if (
            binding is None
            or self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='publication_snapshots'"
            ).fetchone()
            is None
        ):
            return False
        publication = self.db.execute(
            "SELECT issue_date,tasks,body,digest FROM publication_snapshots WHERE run_id=?",
            (binding["run_id"],),
        ).fetchone()
        if publication is None or publication["issue_date"] != edition["issue_date"]:
            return False
        try:
            frozen = json.loads(publication["body"])
            packets = frozen["packets"]
            expected = {"draft": frozen["draft"], "review": frozen["review"]}
            if (
                frozen["notion_required"] is not False
                or frozen["review"]["passed"] is not True
                or canonical_json(expected) != binding["editor_result"]
                or canonical_json(packets) != canonical_json(json.loads(snapshot_json))
                or [packet["id"] for packet in packets] != edition["packet_ids"]
                or publication["digest"]
                != content_hash(
                    {
                        "issue_date": edition["issue_date"],
                        "tasks": json.loads(publication["tasks"]),
                        "result": frozen,
                    }
                )
            ):
                return False
            by_id = {packet["id"]: packet for packet in packets}
            required = json.loads(binding["required_packets"])
            if not required or any(key not in by_id for key in required):
                return False
            for key in required:
                saved = self.db.execute("SELECT body FROM packets WHERE id=?", (key,)).fetchone()
                if (
                    saved is None
                    or canonical_json(json.loads(saved["body"])) != canonical_json(by_id[key])
                    or by_id[key]["content_hash"] != content_hash(by_id[key]["content"])
                ):
                    return False
            validate_draft(frozen["draft"], [by_id[key] for key in required])
            return True
        except (KeyError, TypeError, ValueError):
            return False

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
            self.assert_workflow_research(edition["id"])
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

    def reserve_verification_send(self, request: Payload) -> tuple[EditionRecord, bool]:
        """One explicit corrected-issue verification, separate from daily delivery.

        Never called by cron. The original accepted receipt remains untouched;
        an ambiguous/failed original or verification cannot be bypassed with a
        new key or edition. The same frozen approval is idempotent after restart.
        """
        with self.transaction():
            edition = self.get(request["id"])
            if edition["state"] != "ready":
                raise StoreError("conflict", "Only a ready edition can be verified")
            if edition["rendered"]["render_hash"] != request["expected_render_hash"]:
                raise StoreError("conflict", "Approval does not match the frozen preview")
            reused = self.db.execute(
                "SELECT edition_id,render_hash FROM verification_sends WHERE request_key=?",
                (request["request_key"],),
            ).fetchone()
            if reused and tuple(reused) != (request["id"], request["expected_render_hash"]):
                raise StoreError("conflict", "Verification key belongs to another approval")
            previous = self.db.execute(
                "SELECT edition_id FROM sends WHERE issue_date=?", (edition["issue_date"],)
            ).fetchone()
            if previous is None or previous[0] == edition["id"]:
                raise StoreError("conflict", "Verification requires a distinct delivered issue")
            accepted = "simulated" if self.mode == "mock" else "provider_accepted"
            if self.get(previous[0])["delivery_state"] != accepted:
                raise StoreError("conflict", "Original delivery must have confirmed acceptance")
            row = self.db.execute(
                "SELECT edition_id,render_hash FROM verification_sends WHERE issue_date=?",
                (edition["issue_date"],),
            ).fetchone()
            if row:
                if tuple(row) != (request["id"], request["expected_render_hash"]):
                    raise StoreError("conflict", "This date already has a verification attempt")
                return edition, False
            if edition["delivery_state"] != "not_requested":
                raise StoreError("conflict", "Edition already has a delivery attempt")
            self.assert_workflow_research(edition["id"])
            self.db.execute(
                "INSERT INTO verification_sends VALUES(?,?,?,?,?,?)",
                (
                    edition["issue_date"],
                    edition["id"],
                    request["request_key"],
                    request["expected_render_hash"],
                    previous[0],
                    now(),
                ),
            )
            edition["delivery_state"] = "submitting"
            self._write(edition)
            return edition, True

    def assert_workflow_research(self, edition_id: str) -> None:
        """Enforce the frozen edition's policy, never the latest global setting.

        Legacy editions retain their original Notion gate. Story publications
        need an intact local evidence snapshot instead; a delayed summary copy
        in Notion cannot invalidate independently checked local research.
        """
        with self.lock:
            binding = self.db.execute(
                "SELECT required_packets,projection_required FROM workflow_editions "
                "WHERE edition_id=?",
                (edition_id,),
            ).fetchone()
            if binding is None:
                return
            required = json.loads(binding["required_packets"])
            rows = {
                packet_id: self.db.execute(
                    "SELECT body,projection FROM packets WHERE id=?", (packet_id,)
                ).fetchone()
                for packet_id in required
            }
            if binding["projection_required"]:
                if not required or any(
                    row is None or row["projection"] != "done" for row in rows.values()
                ):
                    raise StoreError(
                        "conflict", "Adopted research must be confirmed in Notion before sending"
                    )
                return
            frozen = self.db.execute(
                "SELECT snapshot FROM editions WHERE id=?", (edition_id,)
            ).fetchone()
            snapshot = json.loads(frozen["snapshot"]) if frozen else []
            packets = {packet["id"]: packet for packet in snapshot}
            if not required or any(
                row is None
                or packet_id not in packets
                or canonical_json(json.loads(row["body"])) != canonical_json(packets[packet_id])
                or packets[packet_id]["content_hash"] != content_hash(packets[packet_id]["content"])
                for packet_id, row in rows.items()
            ):
                raise StoreError("conflict", "Publication requires intact frozen local research")
            try:
                validate_draft(self.get(edition_id)["draft"], [packets[key] for key in required])
            except (KeyError, ValueError):
                raise StoreError(
                    "conflict", "Publication references do not match frozen research"
                ) from None

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
