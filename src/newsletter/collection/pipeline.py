"""One-shot orchestration. A queue wakeup is not a schedule; nothing creates daily jobs."""

import asyncio
from pathlib import Path

from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.collection.collector import Collector
from newsletter.collection.repository import RunRepository
from newsletter.contracts import parse_message, to_dict, validate_request
from newsletter.editor import EditorError
from newsletter.store import StoreError


class CollectionPipeline:
    def __init__(
        self,
        runs: RunRepository,
        collector: Collector,
        workspace: Path,
        timeout: float,
        max_packets: int,
    ) -> None:
        self.runs, self.collector = runs, collector
        self.workspace, self.timeout, self.max_packets = workspace, timeout, max_packets

    async def collect_next(self) -> bool:
        claimed = self.runs.claim()
        if claimed is None:
            return False
        run, instructions = claimed
        count = 0
        current = ""
        try:
            for instruction in instructions:
                current = instruction.id
                self.runs.direction(run["id"], current, state="collecting")
                async with asyncio.timeout(self.timeout):
                    result = await self.collector.collect(
                        instruction, run["issue_date"], self.workspace / run["id"] / current
                    )
                count += len(result.packets)
                if count > self.max_packets or len(result.packets) > 2 or len(result.note) > 2000:
                    raise EditorError("invalid_output")
                requests = []
                for index, material in enumerate(result.packets):
                    request = parse_message(
                        {
                            "request_key": f"{run['id']}:{current}:{index}",
                            "workflow_id": current,
                            "content": material,
                        },
                        pb.PutPacketRequest,
                    )
                    validate_request(request)
                    requests.append(to_dict(request))
                self.runs.save_direction(run["id"], current, requests, result.note)
            self.runs.update(
                run["id"],
                state="projecting" if count else "blocked",
                error_code="" if count else "collection_no_findings",
            )
        except asyncio.CancelledError:
            self.runs.direction(run["id"], current, state="failed")
            self.runs.update(run["id"], state="failed", error_code="collection_interrupted")
            raise
        except TimeoutError:
            self.runs.direction(run["id"], current, state="failed")
            self.runs.update(run["id"], state="failed", error_code="collection_timeout")
        except Exception as exc:
            self.runs.direction(run["id"], current, state="failed")
            code = (
                "collection_" + exc.code
                if isinstance(exc, EditorError)
                else "collection_invalid_result"
            )
            self.runs.update(run["id"], state="failed", error_code=code)
        return True

    def advance(self) -> bool:
        """Proceed only once material projection is confirmed; never retry unknown writes."""
        changed = False
        for run in self.runs.active():
            packet_ids = [
                packet_id
                for direction in run["directions"]
                for packet_id in direction["packet_ids"]
            ]
            if run["state"] == "editing":
                edition = self.runs.store.get(run["edition_id"])
                if edition["state"] in {"failed", "blocked"}:
                    self.runs.update(
                        run["id"],
                        state=edition["state"],
                        error_code=edition.get("error_code", "editor_failed"),
                    )
                    changed = True
                    continue
                if edition["state"] != "ready":
                    continue
                packet_ids = edition["packet_ids"]
            states = self.runs.projection_states(packet_ids)
            if any(state in {"unknown", "failed"} for state in states):
                self.runs.update(
                    run["id"], state="blocked", error_code="notion_projection_unconfirmed"
                )
                changed = True
                continue
            if not all(state == "done" for state in states):
                continue
            if run["state"] == "editing":
                self.runs.update(run["id"], state="ready")
                changed = True
                continue
            try:
                # The edition's own idempotency key survives a crash between these writes.
                edition = self.runs.store.prepare(
                    {
                        "request_key": "collection:" + run["id"],
                        "issue_date": run["issue_date"],
                        "packet_ids": packet_ids,
                    }
                )
            except StoreError as exc:
                if exc.code == "busy":
                    continue  # Existing queued editions will free capacity; no external retry.
                self.runs.update(run["id"], state="failed", error_code="edition_enqueue_failed")
                changed = True
                continue
            self.runs.update(run["id"], state="editing", edition_id=edition["id"])
            changed = True
        return changed
