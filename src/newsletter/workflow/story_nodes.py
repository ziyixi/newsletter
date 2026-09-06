"""Topic preparation with durable, individually approved publication checkpoints.

Provider work stays inside a bounded DAG node. The publication tail is local,
deterministic and can run even when a later provider attempt is interrupted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from newsletter.types import Payload
from newsletter.workflow.engine import NodeContext
from newsletter.workflow.nodes import EditorialNodes
from newsletter.workflow.publication import PublicationRepository, assemble
from newsletter.workflow.sources import identity_keys
from newsletter.workflow.story_editor import StoryEditor
from newsletter.workflow.story_replay import REUSABLE_TYPES, StoryReplay


def freeze_publication(
    publications: PublicationRepository, run_id: str, issue_date: str, *, reason: str
) -> Payload:
    """Never change a publication after its first successful local freeze."""
    previous = publications.get_publication(run_id)
    if previous is not None:
        return previous
    tasks = publications.plan(run_id)
    result = assemble(run_id, issue_date, tasks, publications.results(run_id), reason=reason)
    return publications.record_publication(run_id, issue_date, tasks, result)


def _covered_history(candidates: list[Payload], pending: list[Payload]) -> list[Payload]:
    """Unfinished investigations are not already-covered discovery exclusions.

    Historical aliases inherit the exception, but identities/dates themselves do
    not change. The ordinary discovery, pool and selection deduplicators still
    merge equivalent items within today's pool and suppress other covered topics.
    """
    pending_ids = {candidate_id for story in pending for candidate_id in story["candidate_ids"]}
    pending_keys = set().union(*(identity_keys(story) for story in pending))
    for story in pending:
        for url in story["source_urls"]:
            pending_keys.update(identity_keys({"url": url}))
    remaining = list(candidates)
    while True:
        covered = []
        for candidate in remaining:
            keys = identity_keys(candidate)
            if candidate.get("id") in pending_ids or keys & pending_keys:
                pending_keys.update(keys)
            else:
                covered.append(candidate)
        if len(covered) == len(remaining):
            return covered
        remaining = covered


class StoryNodes(EditorialNodes):
    async def execute(self, kind: str, ctx: NodeContext, path: Path) -> Any:
        if "story_replay" in ctx.run_inputs and kind in REUSABLE_TYPES:
            return StoryReplay(self.store).replay(ctx)
        publications = PublicationRepository(self.store)
        date = ctx.run_inputs["issue_date"]
        if kind == "history":
            history = await super().execute(kind, ctx, path)
            unfinished = ctx.run_inputs.get("pending_stories", [])
            history["candidates"] = _covered_history(history["candidates"], unfinished)
            # These are questions to investigate, never recycled verified claims.
            pending = [
                {
                    "id": item["story_id"],
                    "title": item["title"],
                    "issue_date": item["issue_date"],
                    "question": item["question"],
                    "summary": (
                        "这是未完成调查，不是新发表或新版本；保留真实日期，仍须重新打开原始来源核验。"
                        + item["reason"]
                        + " "
                        + item["evidence_context"]
                    ),
                    "url": next(iter(item["source_urls"]), ""),
                }
                for item in unfinished
            ]
            history["watchlist"] = (pending + history["watchlist"])[:30]
            return history
        if kind == "story_plan":
            tasks = sorted(
                self.one(ctx, "selection")["research_tasks"], key=lambda task: task["priority"]
            )
            publications.save_plan(ctx.run_id, date, tasks)
            # Ranking already considers AI, cross-discipline and world coverage.
            # Every selected task gets a brief before any task gets deepened.
            return {"brief_tasks": tasks, "deep_tasks": tasks[: ctx.params.get("max_deep", 4)]}
        if kind in {"story_brief", "story_deep"}:
            task = cast(Payload, ctx.item)
            mode: Literal["brief", "deep"] = "brief" if kind == "story_brief" else "deep"
            candidates = [
                item
                for item in self.one(ctx, "deduplicate")["candidates"]
                if item["id"] in task["candidate_ids"]
            ]
            prior = publications.best_result(ctx.run_id, task["id"]) if mode == "deep" else None

            def checkpoint(result: Payload) -> None:
                # Commit evidence before its approval receipt. Both operations
                # replay exactly; neither waits for the optional Notion mirror.
                self.store.save_workflow_supplements(ctx.run_id, result["packets"])
                publications.save(ctx.run_id, task, mode, result, issue_date=date)

            result = await StoryEditor(self.editor).prepare(
                task=task,
                candidates=candidates,
                packets=prior["packets"] if prior else [],
                issue_date=date,
                policy=ctx.run_inputs["policy"],
                workspace=path,
                mode=mode,
                prior=prior,
                is_fixture=self.store.mode == "mock",
                on_checkpoint=checkpoint,
            )
            checkpoint(result)
            return result
        if kind == "publish":
            return freeze_publication(publications, ctx.run_id, date, reason="completed")
        return await super().execute(kind, ctx, path)
