"""DAG-to-service integration: durable steps, frozen editions, no sending here."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from newsletter.collection.collector import Collector
from newsletter.collection.instructions import Instruction
from newsletter.collection.pipeline import CollectionPipeline
from newsletter.collection.repository import RunRepository
from newsletter.collection.source_guides import load_discovery_instructions
from newsletter.content_config import (
    config_definition,
    config_instructions,
    load_active,
)
from newsletter.contracts import (
    content_hash,
    validate_draft,
    validate_packet_body,
)
from newsletter.editor import POLICY_DIR, CodexEditor
from newsletter.settings import Settings
from newsletter.store import StoreError
from newsletter.types import Payload
from newsletter.workflow.definition import load_definition, parse_definition
from newsletter.workflow.engine import WorkflowEngine
from newsletter.workflow.nodes import (
    EditorialNodes,
    validate_recipe,
    validate_revision_subgraph,
)
from newsletter.workflow.publication import (
    PublicationError,
    PublicationRepository,
)
from newsletter.workflow.repository import WorkflowError, WorkflowRepository
from newsletter.workflow.state import WorkflowState
from newsletter.workflow.story_nodes import StoryNodes, freeze_publication
from newsletter.workflow.story_recipe import is_story_recipe


def freeze_workflow(
    settings: Settings, state: WorkflowState, issue_date: str
) -> tuple[list[Instruction], Payload]:
    configuration = (
        load_active(settings.content_config_dir)
        if settings.content_config_dir
        else None
    )
    definition = (
        config_definition(configuration)
        if configuration
        else load_definition(settings.workflow_file)
    )
    validate_recipe(definition)
    if (
        settings.notion_backend == "notion"
        and settings.notion_v2
        and not is_story_recipe(definition)
    ):
        raise ValueError(
            "Notion V2 requires the story publication workflow, not legacy projection"
        )
    instructions = (
        config_instructions(configuration["files"])
        if configuration
        else load_discovery_instructions(settings.discovery_dir)
    )
    policy = {}
    for name in ("editorial.md", "reader-profile.md"):
        if configuration:
            policy[name] = configuration["files"]["policy/" + name]
            continue
        filename = (
            "story-editorial.md"
            if name == "editorial.md" and is_story_recipe(definition)
            else name
        )
        path = POLICY_DIR / filename
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 100_000
        ):
            raise ValueError("Invalid editorial policy")
        policy[name] = path.read_text(encoding="utf-8")
    editions = [
        {
            "issue_date": e["issue_date"],
            "title": e.get("draft", {}).get("title", ""),
        }
        for e in state.store.recent_history()
    ]
    return instructions, {
        "definition": definition.snapshot(),
        "inputs": {
            "issue_date": issue_date,
            "instructions": [item.snapshot() for item in instructions],
            "history": state.history(issue_date),
            "pending_stories": PublicationRepository(
                state.store
            ).pending_history(issue_date)
            if is_story_recipe(definition)
            else [],
            "editions": editions,
            "policy": policy,
            "started_at": datetime.now(UTC).isoformat(),
            "timeout_seconds": settings.workflow_timeout_seconds,
            "model": settings.model,
            **({"content_config": configuration} if configuration else {}),
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
        recipe_path: Path | None = None,
    ) -> None:
        super().__init__(runs, collector, workspace, timeout, max_packets)
        self.editor = editor
        self.recipe_path = (
            recipe_path
            or Path(__file__).parents[1] / "workflows" / "daily.yaml"
        )
        self.repository = WorkflowRepository(runs.store)
        self.state = WorkflowState(runs.store)
        self.publications = PublicationRepository(runs.store)

    def has_priority_work(self) -> bool:
        """A new publication's optional Notion mirror cannot consume its deadline."""
        with self.runs.store.lock:
            rows = self.runs.store.db.execute(
                "SELECT body FROM collection_runs WHERE state IN ('queued','collecting')"
            ).fetchall()
        for row in rows:
            run = json.loads(row[0])
            snapshot = self.runs.workflow_snapshot(run["id"])
            if snapshot is not None and is_story_recipe(
                parse_definition(snapshot["definition"])
            ):
                return True
        return False

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
        publication = self.publications.get_publication(run_id)
        if publication is not None:
            run["publication"] = publication["coverage"]
        return run

    def progress(self, run_id: str) -> Payload:
        progress = self.graph_progress(run_id)
        repair = self.state.repair(run_id)
        if repair:
            try:
                continuation = self.graph_progress(repair["child_run_id"])
            except WorkflowError:
                definition = parse_definition(repair["snapshot"]["definition"])
                continuation = {
                    "id": definition.id,
                    "definition_hash": definition.digest,
                    "state": "queued",
                    "nodes": [],
                }
            progress["continuations"] = [continuation]
        return progress

    def graph_progress(self, run_id: str) -> Payload:
        run = self.repository.get(run_id)
        definition = parse_definition(
            self.repository.snapshot(run_id)["definition"]
        )
        nodes = []
        for node in definition.nodes:
            state = run["nodes"][node.id]
            nodes.append(
                {
                    "id": node.id,
                    "type": node.type,
                    "state": state["state"],
                    "completed_items": sum(
                        item["state"] == "succeeded" for item in state["items"]
                    ),
                    "failed_items": sum(
                        item["state"] in {"failed", "unknown"}
                        for item in state["items"]
                    ),
                    "error_code": state["error_code"],
                }
            )
        count = 0
        for node in definition.nodes:
            if (
                node.type == "deduplicate"
                and run["nodes"][node.id]["state"] == "succeeded"
            ):
                count = len(
                    self.repository.output(run_id, node.id)["candidates"]
                )
        return {
            "id": definition.id,
            "definition_hash": definition.digest,
            "state": run["state"],
            "nodes": nodes,
            "candidate_count": count,
            "research_count": sum(
                n["completed_items"]
                for n in nodes
                if n["type"] in {"research", "story_brief", "story_deep"}
            ),
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
            repair = self.state.repair(run["id"])
            execution_id = run["id"]
            if repair:
                snapshot = repair["snapshot"]
                execution_id = repair["child_run_id"]
            definition = parse_definition(snapshot["definition"])
            if repair:
                validate_revision_subgraph(definition)
            else:
                validate_recipe(definition)
            status = self.repository.start(
                execution_id, definition, snapshot["inputs"]
            )
            # A crash may leave completed artifacts without an edition receipt.
            # Recover that local, idempotent tail even after the model deadline.
            if self.finish_graph(run, definition, execution_id, status):
                return True
            elapsed = (
                datetime.now(UTC)
                - datetime.fromisoformat(snapshot["inputs"]["started_at"])
            ).total_seconds()
            remaining = snapshot["inputs"]["timeout_seconds"] - elapsed
            if remaining <= 0:
                if is_story_recipe(definition):
                    self.publish_available(
                        run, definition, reason="workflow_deadline"
                    )
                else:
                    self.runs.update(
                        run["id"],
                        state="blocked",
                        error_code="workflow_deadline",
                    )
                return True
            # The frozen run's model, not a newly edited setting, owns this attempt.
            editor = CodexEditor(
                self.editor.codex_home,
                model=snapshot["inputs"]["model"],
                timeout_seconds=900,
            )
            node_class = (
                StoryNodes if is_story_recipe(definition) else EditorialNodes
            )
            handlers = node_class(
                self.runs.store, definition, editor, self.workspace
            )
            engine = WorkflowEngine(
                self.repository,
                {node.type: handlers for node in definition.nodes},
            )
            try:
                async with asyncio.timeout(remaining):
                    await engine.step(execution_id)
            except TimeoutError:
                if not is_story_recipe(definition):
                    raise
                self.publish_available(
                    run, definition, reason="workflow_deadline"
                )
                return True
            status = self.repository.get(execution_id)
            self.finish_graph(run, definition, execution_id, status)
            return True
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            self.runs.update(
                run["id"], state="blocked", error_code="workflow_deadline"
            )
        except StoreError as error:
            if error.code != "busy":
                self.runs.update(
                    run["id"], state="failed", error_code="workflow_storage"
                )
        except Exception:
            self.runs.update(
                run["id"], state="failed", error_code="workflow_invalid_result"
            )
        return True

    def finish_graph(
        self, run: Payload, definition: Any, execution_id: str, status: Payload
    ) -> bool:
        if is_story_recipe(definition):
            frozen = self.publications.get_publication(run["id"])
            if frozen is not None or status["state"] in {
                "failed",
                "unknown",
                "succeeded",
            }:
                self.publish_available(
                    run,
                    definition,
                    reason="completed"
                    if status["state"] == "succeeded"
                    else "research_interrupted",
                )
                return True
            return False
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
            return True
        if status["state"] == "succeeded":
            self.queue_edition(run, definition, execution_id=execution_id)
            return True
        return False

    def publish_available(
        self, run: Payload, definition: Any, *, reason: str
    ) -> None:
        """A bounded local tail: exact approved units, never another model pass."""
        try:
            if not self.publications.plan(run["id"]):
                raise PublicationError("no_publishable_content")
            snapshot = self.runs.workflow_snapshot(run["id"])
            config = (
                snapshot["inputs"].get("content_config") if snapshot else None
            )
            result = freeze_publication(
                self.publications,
                run["id"],
                run["issue_date"],
                reason=reason,
                max_features=config["editorial"]["max_deep"] if config else 2,
            )
        except PublicationError as error:
            self.runs.update(run["id"], state="blocked", error_code=error.code)
            return
        required = adopted_packets(result["draft"])
        edition = self.runs.store.prepare(
            {
                "request_key": "collection:" + run["id"],
                "issue_date": run["issue_date"],
                "packet_ids": [packet["id"] for packet in result["packets"]],
            },
            workflow_binding={
                "run_id": run["id"],
                "result": {
                    "draft": result["draft"],
                    "review": result["review"],
                },
                "required_packets": required,
                "projection_required": False,
            },
        )
        self.runs.store.finish(edition["id"], publication=result["coverage"])
        self.runs.update(
            run["id"], state="editing", edition_id=edition["id"], error_code=""
        )
        try:
            self.archive_candidates(
                run, definition, required, result["packets"]
            )
        except Exception:
            self.state.archive_result(
                run["id"], error_code="candidate_archive_failed"
            )

    def queue_edition(
        self,
        run: Payload,
        definition: Any,
        *,
        execution_id: str | None = None,
    ) -> None:
        execution_id = execution_id or run["id"]
        review_node = next(
            (node for node in definition.nodes if node.type == "final_review"),
            next(
                (node for node in definition.nodes if node.type == "review"),
                None,
            ),
        )
        if review_node is None:
            raise ValueError("Missing publication review")
        result = self.repository.output(execution_id, review_node.id)
        validate_draft(result["draft"], result["packets"])
        required = adopted_packets(result["draft"])
        edition = self.runs.store.prepare(
            {
                "request_key": "collection:" + execution_id,
                "issue_date": run["issue_date"],
                "packet_ids": [p["id"] for p in result["packets"]],
            },
            workflow_binding={
                "run_id": execution_id,
                "result": {
                    "draft": result["draft"],
                    "review": result["review"],
                },
                "required_packets": required,
            },
        )
        self.runs.update(
            run["id"], state="editing", edition_id=edition["id"], error_code=""
        )
        if execution_id != run["id"]:
            # The original index and research writes already have durable receipts.
            # Never rewrite/recreate them just because a held draft is revised.
            return
        try:
            self.archive_candidates(
                run, definition, required, result["packets"]
            )
        except Exception:
            # Candidate browsing is optional; failure must not discard a frozen
            # edition or hide the separately enforced adopted-material barrier.
            self.state.archive_result(
                run["id"], error_code="candidate_archive_failed"
            )

    def archive_candidates(
        self,
        run: Payload,
        definition: Any,
        required: list[str],
        packets: list[Payload],
    ) -> None:
        from newsletter.workflow.sources import identity_keys

        node = next(
            node for node in definition.nodes if node.type == "deduplicate"
        )
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
        self.state.mark(
            used, "used", "本期正文引用关联的公开来源；不推断读者点击偏好。"
        )
        rows = [
            f"本期 {len(candidates)} 条候选。以下为发现元数据，不是已验证研究结论；邮件只采用部分深读材料。"
        ]
        for index, candidate in enumerate(candidates, 1):
            status = (
                "本期关联采用" if candidate["id"] in used else "候选/继续观察"
            )
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
            if (
                self.runs.workflow_snapshot(run["id"]) is None
                or run["state"] != "editing"
                or not run["edition_id"]
            ):
                continue
            edition = self.runs.store.get(run["edition_id"])
            if edition["state"] in {"failed", "blocked"}:
                self.runs.update(
                    run["id"],
                    state=edition["state"],
                    error_code=edition.get(
                        "error_code", "workflow_editor_failed"
                    ),
                )
                changed = True
                continue
            if edition["state"] != "ready":
                continue
            binding = self.state.edition(edition["id"])
            if binding is not None and binding["projection_required"] is False:
                try:
                    self.state.assert_publishable(edition["id"])
                except StoreError:
                    self.runs.update(
                        run["id"],
                        state="blocked",
                        error_code="publication_evidence_invalid",
                    )
                else:
                    self.runs.update(run["id"], state="ready")
                changed = True
                continue
            states = self.runs.projection_states(
                binding["required_packets"] if binding else []
            )
            if not states or any(
                state in {"failed", "unknown"} for state in states
            ):
                self.runs.update(
                    run["id"],
                    state="blocked",
                    error_code="notion_projection_unconfirmed",
                )
                changed = True
            elif all(state == "done" for state in states):
                self.runs.update(run["id"], state="ready")
                changed = True
        return self.start_legacy_repair() or changed

    def start_legacy_repair(self) -> bool:
        """Resume one old editorial HOLD through a new, frozen two-node subgraph.

        New recipes already contain revision/final_review and never enter here.
        This upgrade bridge changes no old node, edition, request key or receipt.
        It is also crash-resumable between creating the audit record and queueing.
        """
        with self.runs.store.lock:
            pending = self.runs.store.db.execute(
                "SELECT COUNT(*) FROM collection_runs "
                "WHERE state IN ('queued','collecting','projecting','editing')"
            ).fetchone()[0]
            if pending >= self.runs.store.max_pending_jobs:
                return False
            rows = self.runs.store.db.execute(
                "SELECT body FROM collection_runs WHERE state='blocked' "
                "ORDER BY rowid DESC LIMIT 100"
            ).fetchall()
        for row in rows:
            run = json.loads(row[0])
            if run.get(
                "error_code"
            ) != "editorial_review_failed" or not run.get("edition_id"):
                continue
            snapshot = self.runs.workflow_snapshot(run["id"])
            if snapshot is None:
                continue
            try:
                original = parse_definition(snapshot["definition"])
                validate_recipe(original)
                if is_story_recipe(original):
                    continue
                if any(
                    node.type in {"revision", "final_review"}
                    for node in original.nodes
                ):
                    continue  # A second HOLD is terminal, never a third review cycle.
                repair = self.state.repair(run["id"])
                if repair and repair["source_edition_id"] != run["edition_id"]:
                    continue  # The continuation's revised edition also held.
                inputs = snapshot["inputs"]
                elapsed = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(inputs["started_at"])
                ).total_seconds()
                if repair is None and elapsed >= inputs["timeout_seconds"]:
                    continue  # Upgrading must not reset or extend a run's deadline.
                if repair is None:
                    current = load_definition(self.recipe_path)
                    validate_recipe(current)
                    roles = {node.type: node for node in current.nodes}
                    if not {"revision", "final_review"} <= roles.keys():
                        continue
                    definition = parse_definition(
                        {
                            "version": 1,
                            "id": "editorial-repair",
                            "nodes": [
                                {
                                    "id": "revision",
                                    "type": "revision",
                                    "params": roles["revision"].params,
                                },
                                {
                                    "id": "final_review",
                                    "type": "final_review",
                                    "needs": ["revision"],
                                    "params": roles["final_review"].params,
                                },
                            ],
                        }
                    )
                    validate_revision_subgraph(definition)
                    review_node = next(
                        node for node in original.nodes if node.type == "review"
                    )
                    result = self.repository.output(run["id"], review_node.id)
                    binding = self.state.edition(run["edition_id"])
                    if binding is None or binding["result"] != {
                        "draft": result["draft"],
                        "review": result["review"],
                    }:
                        raise ValueError(
                            "Held result does not match its original artifact"
                        )
                    frozen = deepcopy(inputs)
                    frozen.update(
                        prior_review_result=result,
                        parent_run_id=run["id"],
                        parent_definition_hash=original.digest,
                        parent_result_hash=content_hash(result),
                    )
                    repair = self.state.create_repair(
                        run["id"],
                        run["edition_id"],
                        definition.snapshot(),
                        frozen,
                    )
                definition = parse_definition(repair["snapshot"]["definition"])
                validate_revision_subgraph(definition)
                self.repository.start(
                    repair["child_run_id"],
                    definition,
                    repair["snapshot"]["inputs"],
                )
                self.runs.update(run["id"], state="collecting", error_code="")
                return True
            except Exception:
                self.runs.update(
                    run["id"], error_code="workflow_repair_invalid"
                )
                return True
        return False


def adopted_packets(draft: Payload) -> list[str]:
    references = [
        ref
        for section in draft["sections"]
        for paragraph in section["paragraphs"]
        for ref in paragraph["citations"]
    ]
    references += [
        ref
        for point in draft.get("chart", {}).get("points", [])
        for ref in point["citations"]
    ]
    if draft.get("recommended_reading"):
        references.append(draft["recommended_reading"]["citation"])
        references.extend(
            draft["recommended_reading"].get("supporting_citations", [])
        )
    return sorted({ref.split("/", 1)[0] for ref in references})
