"""One serialized editor worker, durable queue, bounded jobs, no automatic publication."""

import asyncio
import json
from pathlib import Path
from typing import cast

from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.adapters import AdapterError, NotionAdapter
from newsletter.collection.pipeline import CollectionPipeline
from newsletter.contracts import (
    content_hash,
    parse_message,
    to_dict,
    validate_draft,
    validate_packet_body,
    validate_personal_digest,
)
from newsletter.editor import Editor, EditorError, EditorResult
from newsletter.email_templates import template_from_inputs
from newsletter.rendering import render_edition
from newsletter.store import Store, now
from newsletter.todofy import DisabledTodofy, TodofyAdapter, unavailable_digest
from newsletter.types import EditionRecord, Payload, RenderResult, ReviewResult
from newsletter.usage import usage_scope
from newsletter.workflow.state import WorkflowState


class Worker:
    def __init__(
        self,
        store: Store,
        editor: Editor,
        notion: NotionAdapter,
        workspace: Path,
        timeout: float,
        *,
        todofy: TodofyAdapter | None = None,
        pipeline: CollectionPipeline | None = None,
        skip_packet_projection: bool = False,
    ) -> None:
        self.store, self.editor, self.notion = store, editor, notion
        self.workspace, self.timeout = workspace, timeout
        self.wake = asyncio.Event()
        self.todofy: TodofyAdapter = todofy or DisabledTodofy()
        self.pipeline = pipeline
        self.skip_packet_projection = skip_packet_projection
        self.workflow_state = WorkflowState(store)

    async def personal_digest(self, edition: EditionRecord) -> Payload:
        try:
            async with asyncio.timeout(50):
                digest = await self.todofy.fetch(edition["issue_date"])
            validate_personal_digest(digest)
            result = to_dict(parse_message(digest, pb.PersonalDigest))
            if not edition["is_fixture"] and result["is_fixture"]:
                return unavailable_digest()
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            return unavailable_digest()

    def frozen_template(self, binding: Payload | None) -> str | None:
        """Resolve the exact execution snapshot, including repairs and replays.

        Older/manual bindings can predate the workflow input ledger entirely;
        only those use the packaged renderer. Invalid new snapshots fail closed
        instead of silently substituting a newer live template.
        """
        if binding is None:
            return None
        with self.store.lock:
            if not self.store.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='workflow_runs'"
            ).fetchone():
                return None
            row = self.store.db.execute(
                "SELECT inputs FROM workflow_runs WHERE id=?", (binding["run_id"],)
            ).fetchone()
        return template_from_inputs(json.loads(row[0])) if row is not None else None

    async def step(self) -> bool:
        if self.pipeline and self.pipeline.advance():
            return True
        claimed = self.store.claim()
        if claimed:
            edition, packets = claimed
            await self.prepare(edition, packets)
            return True
        if self.pipeline and self.pipeline.has_priority_work():
            if await self.pipeline.collect_next():
                return True
        # V2 projects immutable DAG material/edition snapshots independently.
        # Preserve legacy receipts instead of marking unperformed writes done.
        packet = None if self.skip_packet_projection else self.store.claim_projection()
        if packet:
            try:
                async with asyncio.timeout(35):
                    await self.notion.project(packet)
                self.store.projection_result(packet["id"], "done")
            except AdapterError as exc:
                self.store.projection_result(packet["id"], "unknown" if exc.ambiguous else "failed")
            except BaseException as exc:
                self.store.projection_result(packet["id"], "unknown")
                if isinstance(exc, asyncio.CancelledError):
                    raise
            return True
        return await self.pipeline.collect_next() if self.pipeline else False

    async def prepare(self, edition: EditionRecord, packets: list[Payload]) -> None:
        from newsletter.contracts import canonical_json

        try:
            workspace = self.workspace / edition["id"]
            workspace.mkdir(parents=True, mode=0o700, exist_ok=True)
            history = [
                {
                    "issue_date": e["issue_date"],
                    "title": e.get("draft", {}).get("title", ""),
                    "delivery_state": e["delivery_state"],
                }
                for e in self.store.recent_history()
            ]
            (workspace / "recent-history.json").write_text(
                canonical_json(history), encoding="utf-8"
            )
            async with asyncio.timeout(self.timeout):
                binding = self.workflow_state.edition(edition["id"])
                scope_id = binding["run_id"] if binding else edition["id"]
                if binding:
                    frozen = binding["result"]
                    result = EditorResult(frozen["draft"], frozen["review"])
                else:
                    with usage_scope(self.workflow_state.usage_sink(scope_id), "editor"):
                        result = await self.editor.prepare(
                            packets, edition["issue_date"], workspace
                        )
                supplements = []
                for supplied in result.supplemental_packets:
                    packet = to_dict(parse_message(supplied, pb.Packet))
                    validate_packet_body(packet["content"])
                    packet.update(
                        producer_id="editor",
                        workflow_id="editor-research",
                        created_at=now(),
                        is_fixture=edition["is_fixture"],
                        content_hash=content_hash(packet["content"]),
                    )
                    supplements.append(packet)
                all_packets = packets + supplements
                # Shape and citation validation do not certify factual truth.
                validate_draft(result.draft, all_packets)
                draft = to_dict(parse_message(result.draft, pb.Draft))
                review = cast(ReviewResult, to_dict(parse_message(result.review, pb.Review)))
                if len(review["findings"]) > 32 or any(len(f) > 4000 for f in review["findings"]):
                    raise EditorError("invalid_output")
                self.store.save_supplements(edition["id"], supplements)
                if not review["passed"]:
                    self.store.finish(
                        edition["id"],
                        state="blocked",
                        draft=draft,
                        review=review,
                        error_code="editorial_review_failed",
                    )
                    return
            # Separate bounded budget: a slow optional Todofy must not consume
            # the editor's remaining deadline and fail the whole newsletter.
            # Private events never enter prompts, public packets or public search.
            # The separate Notion edition archive requires an explicit opt-in.
            if (
                binding
                and binding.get("projection_required") is False
                and "personal_digest" in edition
            ):
                # A restarted local rendering tail need not regenerate an already
                # completed private Todofy summary. This data never enters a model.
                validate_personal_digest(edition["personal_digest"])
                personal = to_dict(parse_message(edition["personal_digest"], pb.PersonalDigest))
            else:
                personal = await self.personal_digest(edition)
            usage = self.workflow_state.usage(scope_id)
            self.store.finish(edition["id"], personal_digest=personal, usage=usage)
            rendered = await asyncio.to_thread(
                render_edition,
                draft,
                all_packets,
                edition["issue_date"],
                edition["is_fixture"],
                personal_digest=personal,
                usage=usage,
                template_source=self.frozen_template(binding),
            )
            # Freeze precisely the serialized representation returned to the client.
            rendered = cast(RenderResult, to_dict(parse_message(rendered, pb.RenderedEdition)))
            self.store.finish(
                edition["id"], state="ready", draft=draft, review=review, rendered=rendered
            )
        except asyncio.CancelledError:
            self.store.interrupt_preparation(edition["id"])
            raise
        except TimeoutError:
            self.store.finish(edition["id"], state="failed", error_code="editor_timeout")
        except OSError:
            self.store.finish(edition["id"], state="failed", error_code="editor_workspace_error")
        except EditorError as exc:
            self.store.finish(edition["id"], state="failed", error_code=exc.code)
        except Exception:
            # Do not expose provider bodies, source excerpts, tokens, or local paths.
            self.store.finish(edition["id"], state="failed", error_code="editor_invalid_result")

    async def run(self) -> None:
        while True:
            self.wake.clear()
            if await self.step():
                continue
            await self.wake.wait()
