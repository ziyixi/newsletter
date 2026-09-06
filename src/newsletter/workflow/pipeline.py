"""DAG-to-service integration: durable steps, frozen editions, no sending here."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from newsletter.collection.collector import Collector
from newsletter.collection.instructions import Instruction, load_instructions
from newsletter.collection.pipeline import CollectionPipeline
from newsletter.collection.repository import RunRepository
from newsletter.contracts import validate_draft, validate_packet_body
from newsletter.editor import POLICY_DIR, CodexEditor
from newsletter.settings import Settings
from newsletter.store import StoreError
from newsletter.types import Payload
from newsletter.workflow.definition import load_definition, parse_definition
from newsletter.workflow.engine import WorkflowEngine
from newsletter.workflow.nodes import EditorialNodes, validate_recipe
from newsletter.workflow.repository import WorkflowRepository
from newsletter.workflow.state import WorkflowState


def freeze_workflow(
    settings: Settings, state: WorkflowState, issue_date: str
) -> tuple[list[Instruction], Payload]:
    definition = load_definition(settings.workflow_file)
    validate_recipe(definition)
    instructions = load_instructions(settings.discovery_dir)
    policy = {}
    for name in ("editorial.md", "reader-profile.md"):
        path = POLICY_DIR / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
            raise ValueError("Invalid editorial policy")
        policy[name] = path.read_text(encoding="utf-8")
    editions = [
        {"issue_date": e["issue_date"], "title": e.get("draft", {}).get("title", "")}
        for e in state.store.recent_history()
    ]
    return instructions, {
        "definition": definition.snapshot(),
        "inputs": {
            "issue_date": issue_date,
            "instructions": [item.snapshot() for item in instructions],
            "history": state.history(issue_date),
            "editions": editions,
            "policy": policy,
            "started_at": datetime.now(UTC).isoformat(),
            "timeout_seconds": settings.workflow_timeout_seconds,
            "model": settings.model,
        },
    }


class DagPipeline(CollectionPipeline):
    def __init__(
        self,
        runs: RunRepository,
        collector: Collector,
        workspace: Path,
        timeout: float,
        max_packets: int,
        *,
        editor: CodexEditor,
    ) -> None:
        super().__init__(runs, collector, workspace, timeout, max_packets)
        self.editor = editor
        self.repository = WorkflowRepository(runs.store)
        self.state = WorkflowState(runs.store)

    def recover(self) -> None:
        self.repository.recover()

    def receipt(self, run_id: str) -> Payload:
        run = self.runs.get(run_id)
        snapshot = self.runs.workflow_snapshot(run_id)
        if snapshot is None:
            return run
        with self.runs.store.lock:
            exists = self.runs.store.db.execute(
                "SELECT 1 FROM workflow_runs WHERE id=?", (run_id,)
            ).fetchone()
        if exists:
            run["workflow"] = self.progress(run_id)
        else:
            definition = parse_definition(snapshot["definition"])
            run["workflow"] = {
                "id": definition.id,
                "definition_hash": definition.digest,
                "state": "queued",
                "nodes": [],
            }
        run["usage"] = self.state.usage(run_id)
        return run

    def progress(self, run_id: str) -> Payload:
        run = self.repository.get(run_id)
        definition = parse_definition(self.repository.snapshot(run_id)["definition"])
        nodes = []
        for node in definition.nodes:
            state = run["nodes"][node.id]
            nodes.append(
                {
                    "id": node.id,
                    "type": node.type,
                    "state": state["state"],
                    "completed_items": sum(item["state"] == "succeeded" for item in state["items"]),
                    "failed_items": sum(
                        item["state"] in {"failed", "unknown"} for item in state["items"]
                    ),
                    "error_code": state["error_code"],
                }
            )
        count = 0
        for node in definition.nodes:
            if node.type == "deduplicate" and run["nodes"][node.id]["state"] == "succeeded":
                count = len(self.repository.output(run_id, node.id)["candidates"])
        return {
            "id": definition.id,
            "definition_hash": definition.digest,
            "state": run["state"],
            "nodes": nodes,
            "candidate_count": count,
            "research_count": sum(n["completed_items"] for n in nodes if n["type"] == "research"),
        }

    async def collect_next(self) -> bool:
        claimed = self.runs.claim(resume=True)
        if claimed is None:
            return False
        run, _ = claimed
        snapshot = self.runs.workflow_snapshot(run["id"])
        if snapshot is None:
            self.runs.update(run["id"], state="queued")
            return await super().collect_next()
        try:
            definition = parse_definition(snapshot["definition"])
            validate_recipe(definition)
            self.repository.start(run["id"], definition, snapshot["inputs"])
            elapsed = (
                datetime.now(UTC) - datetime.fromisoformat(snapshot["inputs"]["started_at"])
            ).total_seconds()
            remaining = snapshot["inputs"]["timeout_seconds"] - elapsed
            if remaining <= 0:
                self.runs.update(run["id"], state="blocked", error_code="workflow_deadline")
                return True
            # The frozen run's model, not a newly edited setting, owns this attempt.
            editor = CodexEditor(
                self.editor.codex_home, model=snapshot["inputs"]["model"], timeout_seconds=900
            )
            handlers = EditorialNodes(self.runs.store, definition, editor, self.workspace)
            engine = WorkflowEngine(
                self.repository, {node.type: handlers for node in definition.nodes}
            )
            async with asyncio.timeout(remaining):
                await engine.step(run["id"])
            status = self.repository.get(run["id"])
            if status["state"] in {"failed", "unknown"}:
                codes = [
                    node["error_code"]
                    for node in status["nodes"].values()
                    if node["state"] in {"failed", "unknown"}
                ]
                self.runs.update(
                    run["id"],
                    state="blocked",
                    error_code="workflow_" + (codes[0] if codes else "failed"),
                )
            elif status["state"] == "succeeded":
                self.queue_edition(run, definition)
            return True
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            self.runs.update(run["id"], state="blocked", error_code="workflow_deadline")
        except StoreError as error:
            if error.code != "busy":
                self.runs.update(run["id"], state="failed", error_code="workflow_storage")
        except Exception:
            self.runs.update(run["id"], state="failed", error_code="workflow_invalid_result")
        return True

    def queue_edition(self, run: Payload, definition: Any) -> None:
        review_node = next(node for node in definition.nodes if node.type == "review")
        result = self.repository.output(run["id"], review_node.id)
        validate_draft(result["draft"], result["packets"])
        required = adopted_packets(result["draft"])
        edition = self.runs.store.prepare(
            {
                "request_key": "collection:" + run["id"],
                "issue_date": run["issue_date"],
                "packet_ids": [p["id"] for p in result["packets"]],
            },
            workflow_binding={
                "run_id": run["id"],
                "result": {"draft": result["draft"], "review": result["review"]},
                "required_packets": required,
            },
        )
        self.runs.update(run["id"], state="editing", edition_id=edition["id"])
        try:
            self.archive_candidates(run, definition, required, result["packets"])
        except Exception:
            # Candidate browsing is optional; failure must not discard a frozen
            # edition or hide the separately enforced adopted-material barrier.
            self.state.archive_result(run["id"], error_code="candidate_archive_failed")

    def archive_candidates(
        self, run: Payload, definition: Any, required: list[str], packets: list[Payload]
    ) -> None:
        from newsletter.workflow.sources import identity_keys

        node = next(node for node in definition.nodes if node.type == "deduplicate")
        candidates = self.repository.output(run["id"], node.id)["candidates"]
        if not candidates:
            return
        source_keys = set().union(
            *(
                identity_keys({"url": source["url"]})
                for packet in packets
                if packet["id"] in required
                for source in packet["content"]["sources"]
            )
        )
        used = [c["id"] for c in candidates if identity_keys(c) & source_keys]
        self.state.mark(used, "used", "本期正文引用关联的公开来源；不推断读者点击偏好。")
        rows = [
            f"本期 {len(candidates)} 条候选。以下为发现元数据，不是已验证研究结论；邮件只采用部分深读材料。"
        ]
        for index, candidate in enumerate(candidates, 1):
            status = "本期关联采用" if candidate["id"] in used else "候选/继续观察"
            rows.append(
                f"{index}. [{status}] {candidate['title'][:180]}\n{candidate['summary'][:600]}\n为何现在关注：{candidate['why_now'][:300]}\n见来源 {index}；发现元数据尚非结论。"
            )
        body = {
            "title": run["issue_date"] + " · 今日选题池",
            "body": "\n\n".join(rows),
            "sources": [
                {
                    "id": "candidate-" + str(i),
                    "title": c["title"][:500],
                    "url": c["url"],
                    "excerpt": "发现元数据；未在此页认证研究结论。",
                    "access_scope": "metadata",
                    "published_at": c["published_at"],
                }
                for i, c in enumerate(candidates, 1)
            ],
            "tags": ["candidate-index", "unverified", "workflow"],
        }
        validate_packet_body(body)
        packet = self.runs.store.put_packet(
            {
                "request_key": run["id"] + ":candidate-index",
                "workflow_id": "candidate-index",
                "content": body,
            },
            "workflow-index",
        )
        self.state.archive_result(run["id"], packet_id=packet["id"])

    def advance(self) -> bool:
        changed = super().advance()
        for run in self.runs.active():
            if self.runs.workflow_snapshot(run["id"]) is None or not run["edition_id"]:
                continue
            edition = self.runs.store.get(run["edition_id"])
            if edition["state"] in {"failed", "blocked"}:
                self.runs.update(
                    run["id"],
                    state=edition["state"],
                    error_code=edition.get("error_code", "workflow_editor_failed"),
                )
                changed = True
                continue
            if edition["state"] != "ready":
                continue
            binding = self.state.edition(edition["id"])
            states = self.runs.projection_states(binding["required_packets"] if binding else [])
            if not states or any(state in {"failed", "unknown"} for state in states):
                self.runs.update(
                    run["id"], state="blocked", error_code="notion_projection_unconfirmed"
                )
                changed = True
            elif all(state == "done" for state in states):
                self.runs.update(run["id"], state="ready")
                changed = True
        return changed


def adopted_packets(draft: Payload) -> list[str]:
    references = [
        ref
        for section in draft["sections"]
        for paragraph in section["paragraphs"]
        for ref in paragraph["citations"]
    ]
    references += [
        ref for point in draft.get("chart", {}).get("points", []) for ref in point["citations"]
    ]
    if draft.get("recommended_reading"):
        references.append(draft["recommended_reading"]["citation"])
    return sorted({ref.split("/", 1)[0] for ref in references})
