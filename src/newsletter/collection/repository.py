"""Durable run receipts and instruction snapshots, sharing the service transaction lock."""

import json
from uuid import uuid4

from newsletter.collection.instructions import Instruction
from newsletter.contracts import canonical_json, content_hash
from newsletter.store import Store, StoreError, now
from newsletter.types import Payload


class RunRepository:
    def __init__(self, store: Store) -> None:
        self.store = store
        with store.lock:
            store.db.execute("""CREATE TABLE IF NOT EXISTS collection_runs (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                request_hash TEXT NOT NULL, state TEXT NOT NULL,
                body TEXT NOT NULL, instructions TEXT NOT NULL)""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS collection_workflow_snapshots (
                run_id TEXT PRIMARY KEY, body TEXT NOT NULL)""")

    def existing(self, request: Payload) -> Payload | None:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT request_hash,body FROM collection_runs WHERE request_key=?",
                (request["request_key"],),
            ).fetchone()
            if row is None:
                return None
            if row["request_hash"] != content_hash(request):
                raise StoreError("conflict", "request_key was used for a different run")
            return json.loads(row["body"])

    def start(
        self,
        request: Payload,
        instructions: list[Instruction],
        *,
        workflow_snapshot: Payload | None = None,
    ) -> Payload:
        with self.store.transaction():
            return self._start(request, instructions, workflow_snapshot=workflow_snapshot)

    def _start(
        self,
        request: Payload,
        instructions: list[Instruction],
        *,
        workflow_snapshot: Payload | None = None,
    ) -> Payload:
        """Internal transaction-owned creation, also used by audited continuations."""
        if previous := self.existing(request):
            return previous
        count = self.store.db.execute(
            "SELECT COUNT(*) FROM collection_runs WHERE state IN ('queued','collecting','projecting','editing')"
        ).fetchone()[0]
        if count >= self.store.max_pending_jobs:
            raise StoreError("busy", "Collection queue is full")
        snapshot = [item.snapshot() for item in instructions]
        at = now()
        run: Payload = {
            "id": str(uuid4()),
            "issue_date": request["issue_date"],
            "state": "queued",
            "instructions_hash": content_hash(snapshot),
            "directions": [
                {
                    "id": item.id,
                    "instruction_hash": item.digest,
                    "state": "queued",
                    "packet_ids": [],
                    "note": "",
                }
                for item in instructions
            ],
            "edition_id": "",
            "error_code": "",
            "created_at": at,
            "updated_at": at,
            "is_fixture": self.store.mode == "mock",
        }
        self.store.db.execute(
            "INSERT INTO collection_runs VALUES (?,?,?,?,?,?)",
            (
                run["id"],
                request["request_key"],
                content_hash(request),
                run["state"],
                canonical_json(run),
                canonical_json(snapshot),
            ),
        )
        if workflow_snapshot is not None:
            self.store.db.execute(
                "INSERT INTO collection_workflow_snapshots VALUES(?,?)",
                (run["id"], canonical_json(workflow_snapshot)),
            )
        return run

    def workflow_snapshot(self, run_id: str) -> Payload | None:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT body FROM collection_workflow_snapshots WHERE run_id=?", (run_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, run_id: str) -> Payload:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT body FROM collection_runs WHERE id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise StoreError("not_found", "Run not found")
            return json.loads(row[0])

    def _write(self, run: Payload) -> None:
        run["updated_at"] = now()
        self.store.db.execute(
            "UPDATE collection_runs SET state=?,body=? WHERE id=?",
            (run["state"], canonical_json(run), run["id"]),
        )

    def update(self, run_id: str, **fields: object) -> Payload:
        with self.store.transaction():
            run = self.get(run_id)
            run.update(fields)
            self._write(run)
            return run

    def direction(self, run_id: str, direction_id: str, **fields: object) -> None:
        with self.store.transaction():
            run = self.get(run_id)
            direction = next(d for d in run["directions"] if d["id"] == direction_id)
            direction.update(fields)
            self._write(run)

    def claim(self, *, resume: bool = False) -> tuple[Payload, list[Instruction]] | None:
        with self.store.transaction():
            row = self.store.db.execute(
                "SELECT body,instructions FROM collection_runs WHERE state IN ('queued','collecting') ORDER BY rowid LIMIT 1"
                if resume
                else "SELECT body,instructions FROM collection_runs WHERE state='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            run = json.loads(row["body"])
            run["state"] = "collecting"
            self._write(run)
            return run, [Instruction(**item) for item in json.loads(row["instructions"])]

    def save_direction(
        self, run_id: str, direction_id: str, requests: list[Payload], note: str
    ) -> None:
        """Validated materials and their run association commit together or not at all."""
        with self.store.transaction():
            packet_ids = [
                self.store._put_packet(request, "collector")["id"] for request in requests
            ]
            run = self.get(run_id)
            direction = next(d for d in run["directions"] if d["id"] == direction_id)
            direction.update(
                state="collected" if packet_ids else "no_findings", packet_ids=packet_ids, note=note
            )
            self._write(run)

    def active(self) -> list[Payload]:
        with self.store.lock:
            return [
                json.loads(row[0])
                for row in self.store.db.execute(
                    "SELECT body FROM collection_runs WHERE state IN ('projecting','editing') ORDER BY rowid"
                ).fetchall()
            ]

    def recover(self) -> None:
        # Never reissue an interrupted model request or ambiguous Notion write.
        with self.store.transaction():
            rows = self.store.db.execute(
                "SELECT body FROM collection_runs WHERE state='collecting'"
            ).fetchall()
            for row in rows:
                run = json.loads(row[0])
                if self.workflow_snapshot(run["id"]):
                    # DAG attempts decide whether work is safe to resume; already
                    # completed stages are immutable, in-flight attempts become unknown.
                    run.update(state="queued", error_code="")
                    self._write(run)
                    continue
                run.update(state="failed", error_code="collection_interrupted")
                for direction in run["directions"]:
                    if direction["state"] == "collecting":
                        direction["state"] = "failed"
                self._write(run)

    def projection_states(self, packet_ids: list[str]) -> list[str]:
        with self.store.lock:
            states = []
            for packet_id in packet_ids:
                row = self.store.db.execute(
                    "SELECT projection FROM packets WHERE id=?", (packet_id,)
                ).fetchone()
                states.append(row[0] if row else "failed")
            return states
