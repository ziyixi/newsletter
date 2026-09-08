"""One explicit, audited restart of story writers after a shared startup failure.

The terminal parent is immutable. Its successful upstream artifacts are read as
untrusted research inputs by local child attempts, never reissued to providers.
No source approval, publication, Notion operation or delivery can be replayed.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.collection.instructions import Instruction
from newsletter.collection.repository import RunRepository
from newsletter.contracts import canonical_json, content_hash, parse_message, validate_request
from newsletter.editor import EditorError
from newsletter.store import Store, StoreError, now
from newsletter.types import Payload
from newsletter.workflow.content import parse_plan
from newsletter.workflow.definition import parse_definition
from newsletter.workflow.engine import NodeContext
from newsletter.workflow.publication import PublicationRepository, validate_result
from newsletter.workflow.repository import WorkflowError, WorkflowRepository
from newsletter.workflow.story_recipe import validate_story_recipe

REUSABLE_TYPES = frozenset(
    {"history", "api_feed", "discovery", "deduplicate", "selection", "story_plan"}
)


def _conflict() -> StoreError:
    return StoreError("conflict", "Story restart requires intact, eligible frozen source receipts")


class StoryReplay:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.runs = RunRepository(store)
        self.workflows = WorkflowRepository(store)
        self.publications = PublicationRepository(store)
        with store.lock:
            store.db.execute(
                "CREATE TABLE IF NOT EXISTS workflow_story_replays ("
                "parent_run_id TEXT PRIMARY KEY, child_run_id TEXT UNIQUE NOT NULL, "
                "request_key TEXT UNIQUE NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL)"
            )

    def start(self, parent_id: str, request: Payload) -> Payload:
        """Atomically create at most one child; a repeated request never resets it."""
        validate_request(parse_message({"id": parent_id}, pb.GetRunRequest))
        validate_request(parse_message(request, pb.StartRunRequest))
        with self.store.transaction():
            row = self.store.db.execute(
                "SELECT * FROM workflow_story_replays WHERE parent_run_id=?", (parent_id,)
            ).fetchone()
            if row is not None:
                receipt = self._receipt(row)
                if receipt["request"] != request:
                    raise _conflict()
                return self.runs.get(receipt["child_run_id"])
            if (
                self.runs.existing(request) is not None
                or self.store.db.execute(
                    "SELECT 1 FROM workflow_story_replays WHERE child_run_id=?", (parent_id,)
                ).fetchone()
            ):
                raise _conflict()
            snapshot, manifest = self._source(parent_id)
            if request["issue_date"] != snapshot["inputs"]["issue_date"]:
                raise _conflict()
            child_snapshot = deepcopy(snapshot)
            child_snapshot["inputs"].update(started_at=now(), story_replay=manifest)
            instructions = [Instruction(**item) for item in snapshot["inputs"]["instructions"]]
            child = self.runs._start(request, instructions, workflow_snapshot=child_snapshot)
            receipt = {
                "parent_run_id": parent_id,
                "child_run_id": child["id"],
                "request": deepcopy(request),
                "snapshot_hash": content_hash(child_snapshot),
                "manifest": manifest,
                "created_at": now(),
            }
            self.store.db.execute(
                "INSERT INTO workflow_story_replays VALUES(?,?,?,?,?)",
                (
                    parent_id,
                    child["id"],
                    request["request_key"],
                    canonical_json(receipt),
                    content_hash(receipt),
                ),
            )
            return child

    def _receipt(self, row: Any) -> Payload:
        receipt = json.loads(row["body"])
        snapshot = self.runs.workflow_snapshot(row["child_run_id"])
        if (
            content_hash(receipt) != row["digest"]
            or receipt["parent_run_id"] != row["parent_run_id"]
            or receipt["child_run_id"] != row["child_run_id"]
            or receipt["request"]["request_key"] != row["request_key"]
            or snapshot is None
            or content_hash(snapshot) != receipt["snapshot_hash"]
            or snapshot["inputs"].get("story_replay") != receipt["manifest"]
        ):
            raise _conflict()
        return receipt

    def _source(self, parent_id: str) -> tuple[Payload, Payload]:
        """Check eligibility and all source hashes without mutating the parent."""
        try:
            return self._validated_source(parent_id)
        except (KeyError, TypeError, ValueError, EditorError, WorkflowError):
            raise _conflict() from None

    def _validated_source(self, parent_id: str) -> tuple[Payload, Payload]:
        parent = self.runs.get(parent_id)
        snapshot = self.runs.workflow_snapshot(parent_id)
        graph = self.workflows.get(parent_id)
        frozen = self.workflows.snapshot(parent_id)
        definition = parse_definition(frozen["definition"])
        validate_story_recipe(definition)
        if (
            parent["state"] != "blocked"
            or parent["error_code"] != "no_publishable_content"
            or parent["edition_id"]
            or graph["state"] not in {"failed", "succeeded"}
            or snapshot != {"definition": frozen["definition"], "inputs": frozen["inputs"]}
            or definition.digest != frozen["definition_hash"]
            or content_hash(frozen["inputs"]) != frozen["inputs_hash"]
            or graph["definition_hash"] != frozen["definition_hash"]
            or graph["inputs_hash"] != frozen["inputs_hash"]
            or "story_replay" in frozen["inputs"]
            or parent["issue_date"] != frozen["inputs"]["issue_date"]
            or self.publications.get_publication(parent_id) is not None
            or self.store.db.execute(
                "SELECT 1 FROM workflow_editions WHERE run_id=?", (parent_id,)
            ).fetchone()
        ):
            raise _conflict()
        instruction_row = self.store.db.execute(
            "SELECT instructions FROM collection_runs WHERE id=?", (parent_id,)
        ).fetchone()
        instructions = json.loads(instruction_row[0])
        if (
            instructions != frozen["inputs"]["instructions"]
            or content_hash(instructions) != parent["instructions_hash"]
            or any(content_hash(item["text"]) != item["digest"] for item in instructions)
        ):
            raise _conflict()

        roles = {node.type: node for node in definition.nodes}
        upstream = {node.id: node for node in definition.nodes if node.type in REUSABLE_TYPES}
        artifacts = self.workflows.artifacts(parent_id)
        indexed = {(item["node_id"], item["item_id"]): item for item in artifacts}
        attempts = self.workflows.attempts(parent_id)
        attempt_map = {(item["node_id"], item["item_id"]): item for item in attempts}
        manifest_artifacts = []
        for node_id in sorted(upstream):
            node = upstream[node_id]
            state = graph["nodes"][node_id]
            if state["state"] != "succeeded" or state["degraded"]:
                raise _conflict()
            dependencies = {key: indexed[(key, "")]["value"] for key in node.needs}
            if node.map is not None:
                parts = node.map.source.split(".")
                items = frozen["inputs"] if parts[0] == "run" else dependencies[parts[0]]
                for part in parts[1:]:
                    items = items[part]
                if (
                    not state["map_expanded"]
                    or state["map_hash"] != content_hash(items)
                    or [item["value"] for item in state["items"]] != items
                    or [item["id"] for item in state["items"]] != [item["id"] for item in items]
                ):
                    raise _conflict()
            elif state["map_expanded"] or state["items"]:
                raise _conflict()
            targets = [("", state)] + [(item["id"], item) for item in state["items"]]
            for item_id, target in targets:
                artifact = indexed[(node_id, item_id)]
                digest = content_hash(artifact["value"])
                identifier = content_hash(
                    {"run": parent_id, "node": node_id, "item": item_id, "hash": digest}
                )
                if (
                    target["state"] != "succeeded"
                    or target["artifact_id"] != artifact["id"]
                    or artifact["id"] != identifier
                    or artifact["content_hash"] != digest
                ):
                    raise _conflict()
                if item_id or not state["map_expanded"]:
                    attempt = attempt_map[(node_id, item_id)]
                    if (
                        attempt["state"] != "succeeded"
                        or attempt["artifact_id"] != identifier
                        or attempt["input_hash"]
                        != content_hash(
                            {
                                "definition_hash": definition.digest,
                                "params": node.params,
                                "inputs": dependencies,
                                "run_inputs": frozen["inputs"],
                                "item": target["value"] if item_id else None,
                            }
                        )
                    ):
                        raise _conflict()
                manifest_artifacts.append(
                    {
                        "node_id": node_id,
                        "item_id": item_id,
                        "artifact_id": identifier,
                        "content_hash": digest,
                    }
                )
        candidates = indexed[(roles["deduplicate"].id, "")]["value"]["candidates"]
        for candidate in candidates:
            parse_message(candidate, pb.Candidate)
        selected = indexed[(roles["selection"].id, "")]["value"]
        tasks = parse_plan(
            canonical_json(
                {"research_tasks": selected["research_tasks"], "note": selected["note"]}
            ),
            {item["id"] for item in candidates},
            {item["url"] for item in candidates},
            roles["selection"].params.get("max_tasks", 8),
        ).research_tasks
        plan = indexed[(roles["story_plan"].id, "")]["value"]
        deep_limit = roles["story_plan"].params.get("max_deep", 4)
        configuration = frozen["inputs"].get("content_config")
        if configuration is not None:
            deep_limit = min(deep_limit, configuration["editorial"]["max_deep"])
        if (
            not tasks
            or self.publications.plan(parent_id) != tasks
            or plan["brief_tasks"] != tasks
            or plan["deep_tasks"] != tasks[:deep_limit]
        ):
            raise _conflict()
        results = self.publications.results(parent_id)
        for value in results:
            validate_result(value)
            if (
                value["content"] is not None
                or value["signal"] is not None
                or value["assessments"]
                or value.get("withdrawals")
                or value["packets"]
                or value["reason"] != "editor_unavailable"
                or value["issues"]
                != [
                    {
                        "round": "service",
                        "component": "body",
                        "claim": "",
                        "reason": "writer:unavailable",
                        "evidence": [],
                        "action": "research",
                    }
                ]
            ):
                raise _conflict()
        story_ids = {roles[kind].id for kind in ("story_brief", "story_deep")}
        story_attempts = [attempt for attempt in attempts if attempt["node_id"] in story_ids]
        configuration = (
            len(story_attempts) == 1
            and story_attempts[0]["state"] == "failed"
            and story_attempts[0]["node_id"] == roles["story_brief"].id
            and story_attempts[0]["error_code"] == "configuration"
            and not results
        )
        unavailable = (
            bool(story_attempts)
            and all(attempt["state"] == "succeeded" for attempt in story_attempts)
            and {(value["story_id"], value["mode"]) for value in results}
            == {(task["id"], "brief") for task in tasks}
            | {(task["id"], "deep") for task in plan["deep_tasks"]}
            and len(results) == len(story_attempts)
        )
        for attempt in story_attempts:
            if attempt["state"] == "succeeded":
                artifact = indexed[(attempt["node_id"], attempt["item_id"])]
                digest = content_hash(artifact["value"])
                if (
                    artifact["content_hash"] != digest
                    or artifact["id"] != attempt["artifact_id"]
                    or artifact["id"]
                    != content_hash(
                        {
                            "run": parent_id,
                            "node": attempt["node_id"],
                            "item": attempt["item_id"],
                            "hash": digest,
                        }
                    )
                    or artifact["value"] not in results
                ):
                    raise _conflict()
        # Missing token reports are not zero consumption. Retain the original
        # failed invocation records in lineage totals, including partial flags.
        # This bridge only accepts a single failed startup turn per story.
        # A timeout, account limit or actual editorial rejection is not eligible.
        usage = [
            value
            for row in self.store.db.execute(
                "SELECT body FROM model_usage WHERE scope_id=?", (parent_id,)
            ).fetchall()
            if (value := json.loads(row[0]))["stage"].split(":")[0] in story_ids
        ]
        stages = {attempt["node_id"] + ":" + attempt["item_id"] for attempt in story_attempts}
        if (
            not (configuration or unavailable)
            or any(
                value["stage"] not in stages
                or value["status"] != "failed"
                or value["usage"] is not None
                or value["usage_events"] != 0
                or value["turns_with_usage"] != 0
                or value["turns_started"] != 1
                or value["turns_completed"] not in {0, 1}
                or (unavailable and value["turns_completed"] != 1)
                for value in usage
            )
            or len({value["stage"] for value in usage}) != len(usage)
            or (unavailable and {value["stage"] for value in usage} != stages)
        ):
            raise _conflict()
        if snapshot is None:
            raise _conflict()
        return snapshot, {
            "parent_run_id": parent_id,
            "definition_hash": frozen["definition_hash"],
            "inputs_hash": frozen["inputs_hash"],
            "tasks_hash": content_hash(tasks),
            "failure_hash": content_hash({"attempts": story_attempts, "results": results}),
            "artifacts": manifest_artifacts,
            "reason": "shared_writer_configuration"
            if configuration
            else "writer_startup_unavailable",
        }

    def replay(self, ctx: NodeContext) -> Any:
        """A real local attempt verifies and imports one exact upstream result."""
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT * FROM workflow_story_replays WHERE child_run_id=?", (ctx.run_id,)
            ).fetchone()
            if row is None:
                raise _conflict()
            receipt = self._receipt(row)
            snapshot, manifest = self._source(receipt["parent_run_id"])
            child_snapshot = self.runs.workflow_snapshot(ctx.run_id)
            if (
                manifest != receipt["manifest"]
                or child_snapshot is None
                or ctx.run_inputs != child_snapshot["inputs"]
                or ctx.run_inputs.get("story_replay") != manifest
            ):
                raise _conflict()
            definition = parse_definition(snapshot["definition"])
            node = next(node for node in definition.nodes if node.id == ctx.node_id)
            if node.type not in REUSABLE_TYPES:
                raise _conflict()
            source = next(
                item
                for item in self.workflows.artifacts(receipt["parent_run_id"], ctx.node_id)
                if item["item_id"] == ctx.item_id
            )
            value = deepcopy(source["value"])
        if node.type == "story_plan":
            self.publications.save_plan(
                ctx.run_id, ctx.run_inputs["issue_date"], value["brief_tasks"]
            )
        return value
