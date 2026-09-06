"""Serial logical-node execution; implementations are explicitly supplied by code.

No scheduler, dynamic imports, expressions, provider credentials, or publication
live here. Handlers can perform bounded internal retrieval parallelism themselves.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from newsletter.workflow.definition import NODE_TYPES, NodeDefinition, parse_definition
from newsletter.workflow.repository import (
    ERROR_CODES,
    SUCCESS_STATES,
    WorkflowError,
    WorkflowRepository,
)


@dataclass(frozen=True)
class NodeContext:
    run_id: str
    node_id: str
    item_id: str
    params: dict[str, Any]
    inputs: dict[str, Any]
    run_inputs: dict[str, Any]
    dependency_states: dict[str, Any] = field(default_factory=dict)
    item: dict[str, Any] | None = None
    context: Any = None


@dataclass(frozen=True)
class NodeResult:
    value: Any = None
    state: str = "succeeded"
    error_code: str = ""

    @classmethod
    def skipped(cls, value: Any = None, code: str = "no_findings") -> "NodeResult":
        return cls(value, "skipped", code)


class NodeFailure(RuntimeError):
    def __init__(self, code: str = "handler_failed", *, ambiguous: bool = False) -> None:
        self.code = code if code in ERROR_CODES else "handler_failed"
        self.ambiguous = ambiguous
        super().__init__("Workflow node failed: " + self.code)


NodeHandler = Callable[[NodeContext], Awaitable[NodeResult | Any]]


@dataclass
class WorkflowEngine:
    repository: WorkflowRepository
    handlers: Mapping[str, NodeHandler]
    context: Any = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if set(self.handlers) - NODE_TYPES or any(
            not callable(handler) for handler in self.handlers.values()
        ):
            raise NodeFailure("configuration")

    async def run(self, run_id: str) -> dict[str, Any]:
        while await self.run_step(run_id):
            pass
        return self.repository.get(run_id)

    async def step(self, run_id: str) -> bool:
        return await self.run_step(run_id)

    async def run_step(self, run_id: str) -> bool:
        """Advance one expansion or one persisted attempt; completed work is never replayed."""
        async with self._lock:
            run = self.repository.get(run_id)
            if run["state"] not in {"queued", "running"}:
                return False
            snapshot = self.repository.snapshot(run_id)
            definition = parse_definition(snapshot["definition"])
            for node in definition.nodes:
                state = run["nodes"][node.id]
                if state["state"] not in {"pending", "running"}:
                    continue
                if any(
                    run["nodes"][dependency]["state"] not in SUCCESS_STATES
                    for dependency in node.needs
                ):
                    continue
                inputs = {
                    dependency: self.repository.output(run_id, dependency)
                    for dependency in node.needs
                }
                if node.map and not state["map_expanded"]:
                    try:
                        items = self._items(node, inputs, snapshot["inputs"])
                        self.repository.expand_map(run_id, node.id, items)
                    except (NodeFailure, WorkflowError):
                        attempt = self.repository.claim(run_id, node.id, "", {"invalid_map": True})
                        if attempt:
                            self.repository.finish(attempt, "failed", error_code="invalid_input")
                        return attempt is not None
                    return True
                item = None
                if node.map:
                    item = next(
                        (entry for entry in state["items"] if entry["state"] == "pending"), None
                    )
                    if item is None:
                        continue
                elif state["state"] != "pending":
                    continue
                context = NodeContext(
                    run_id=run_id,
                    node_id=node.id,
                    item_id=item["id"] if item else "",
                    params=node.params,
                    inputs=inputs,
                    run_inputs=snapshot["inputs"],
                    dependency_states={
                        dependency: run["nodes"][dependency] for dependency in node.needs
                    },
                    item=item["value"] if item else None,
                    context=self.context,
                )
                attempt = self.repository.claim(
                    run_id,
                    node.id,
                    context.item_id,
                    {
                        "definition_hash": definition.digest,
                        "params": context.params,
                        "inputs": context.inputs,
                        "run_inputs": context.run_inputs,
                        "item": context.item,
                    },
                )
                if attempt is None:
                    continue
                await self._execute(node, context, attempt)
                return True
            return False

    @staticmethod
    def _items(node: NodeDefinition, inputs: dict[str, Any], run_inputs: dict[str, Any]) -> Any:
        if node.map is None:
            raise NodeFailure("configuration")
        parts = node.map.source.split(".")
        value: Any = run_inputs if parts[0] == "run" else inputs.get(parts[0])
        for key in parts[1:]:
            if not isinstance(value, dict) or key not in value:
                raise NodeFailure("invalid_input")
            value = value[key]
        return value

    async def _execute(self, node: NodeDefinition, context: NodeContext, attempt: str) -> None:
        try:
            handler = self.handlers.get(node.type)
            if handler is None:
                raise NodeFailure("configuration")
            output = await handler(context)
            result = output if isinstance(output, NodeResult) else NodeResult(output)
            if result.state not in SUCCESS_STATES or (
                result.error_code and result.error_code not in ERROR_CODES
            ):
                raise NodeFailure("invalid_output")
            self.repository.finish(attempt, result.state, result.value, result.error_code)
        except asyncio.CancelledError:
            self.repository.finish(attempt, "unknown", error_code="interrupted")
            raise
        except TimeoutError:
            self.repository.finish(attempt, "unknown", error_code="timeout")
        except NodeFailure as error:
            self.repository.finish(
                attempt, "unknown" if error.ambiguous else "failed", error_code=error.code
            )
        except Exception:
            self.repository.finish(attempt, "failed", error_code="handler_failed")
