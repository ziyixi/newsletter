"""A bounded YAML data format, not an executable workflow language.

Node implementations and their parameter schemas live in trusted application
code. YAML cannot register code, expand environment variables or grant sending.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from newsletter.contracts import canonical_json, content_hash

MAX_DEFINITION_BYTES = 65_536
MAX_NODES = 32
MAX_MAP_ITEMS = 32
MAX_TOTAL_TASKS = 128
NODE_TYPES = frozenset(
    {
        "discovery",
        "api_feed",
        "history",
        "deduplicate",
        "selection",
        "research",
        "composition",
        "gap_plan",
        "finalization",
        "review",
        "revision",
        "final_review",
        "story_plan",
        "story_brief",
        "story_deep",
        "publish",
    }
)
CONTINUE_TYPES = frozenset(
    {"discovery", "api_feed", "history", "research", "story_brief", "story_deep"}
)
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_FORBIDDEN_KEYS = frozenset(
    {
        "command",
        "shell",
        "script",
        "exec",
        "python",
        "module",
        "callable",
        "env",
        "environment",
        "secret",
        "secrets",
        "password",
        "api_key",
        "token",
        "access_token",
        "refresh_token",
    }
)


class DefinitionError(ValueError):
    """Fixed diagnostics never include YAML contents or operator values."""

    def __init__(self) -> None:
        super().__init__(
            "Invalid workflow definition: use version 1, registered node types, unique IDs, "
            "acyclic dependencies and bounded literal parameters/maps."
        )


def _parameters(value: object, depth: int = 0) -> None:
    if depth > 8:
        raise DefinitionError()
    if value is None or isinstance(value, (str, bool, int, float)):
        return
    if isinstance(value, list) and len(value) <= 64:
        for item in value:
            _parameters(item, depth + 1)
        return
    if isinstance(value, dict) and len(value) <= 64:
        for key, item in value.items():
            if not isinstance(key, str) or key.lower() in _FORBIDDEN_KEYS:
                raise DefinitionError()
            _parameters(item, depth + 1)
        return
    raise DefinitionError()


@dataclass(frozen=True)
class MapDefinition:
    source: str
    max_items: int


@dataclass(frozen=True)
class NodeDefinition:
    id: str
    type: str
    needs: tuple[str, ...]
    params_json: str = "{}"
    map: MapDefinition | None = None
    on_error: str = "stop"

    @property
    def params(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.params_json))

    def snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "needs": list(self.needs),
            "params": self.params,
            "on_error": self.on_error,
        }
        if self.map:
            result["map"] = {"from": self.map.source, "max_items": self.map.max_items}
        return result


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    nodes: tuple[NodeDefinition, ...]
    version: int = 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "nodes": [node.snapshot() for node in self.nodes],
        }

    @property
    def digest(self) -> str:
        return content_hash(self.snapshot())


def parse_definition(value: object) -> WorkflowDefinition:
    """Validate a semantic snapshot too; persisted definitions do not bypass checks."""
    try:
        return _parse_definition(value)
    except (KeyError, TypeError, ValueError, RecursionError, OverflowError):
        raise DefinitionError() from None


def _parse_definition(value: object) -> WorkflowDefinition:
    if not isinstance(value, dict) or set(value) != {"version", "id", "nodes"}:
        raise DefinitionError()
    if type(value["version"]) is not int or value["version"] != 1:
        raise DefinitionError()
    if not isinstance(value["id"], str) or not _ID.fullmatch(value["id"]):
        raise DefinitionError()
    items = value["nodes"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_NODES:
        raise DefinitionError()
    nodes = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {
            "id",
            "type",
            "needs",
            "params",
            "map",
            "on_error",
        }:
            raise DefinitionError()
        identifier, kind = item["id"], item["type"]
        if not isinstance(identifier, str) or not _ID.fullmatch(identifier) or identifier == "run":
            raise DefinitionError()
        if not isinstance(kind, str) or kind not in NODE_TYPES:
            raise DefinitionError()
        on_error = item.get("on_error", "stop")
        if on_error not in {"stop", "continue"} or (
            on_error == "continue" and kind not in CONTINUE_TYPES
        ):
            raise DefinitionError()
        needs = item.get("needs", [])
        if (
            not isinstance(needs, list)
            or len(needs) > MAX_NODES
            or any(not isinstance(dep, str) or not _ID.fullmatch(dep) for dep in needs)
            or len(set(needs)) != len(needs)
            or identifier in needs
        ):
            raise DefinitionError()
        params = item.get("params", {})
        if not isinstance(params, dict):
            raise DefinitionError()
        _parameters(params)
        params_json = canonical_json(params)
        if len(params_json.encode("utf-8")) > 8192:
            raise DefinitionError()
        mapping = None
        if "map" in item:
            mapping = item["map"]
            if not isinstance(mapping, dict) or set(mapping) != {"from", "max_items"}:
                raise DefinitionError()
            source, maximum = mapping["from"], mapping["max_items"]
            if (
                not isinstance(source, str)
                or type(maximum) is not int
                or not 1 <= maximum <= MAX_MAP_ITEMS
            ):
                raise DefinitionError()
            parts = source.split(".")
            if not 2 <= len(parts) <= 4 or not _ID.fullmatch(parts[0]):
                raise DefinitionError()
            if any(not _FIELD.fullmatch(field) for field in parts[1:]):
                raise DefinitionError()
            if parts[0] != "run" and parts[0] not in needs:
                raise DefinitionError()
            mapping = MapDefinition(source, maximum)
        nodes.append(NodeDefinition(identifier, kind, tuple(needs), params_json, mapping, on_error))
    by_id = {node.id: node for node in nodes}
    if len(by_id) != len(nodes) or any(set(node.needs) - by_id.keys() for node in nodes):
        raise DefinitionError()
    completed: set[str] = set()
    while len(completed) < len(nodes):
        ready = {node.id for node in nodes if set(node.needs) <= completed} - completed
        if not ready:
            raise DefinitionError()
        completed.update(ready)
    if sum(node.map.max_items if node.map else 1 for node in nodes) > MAX_TOTAL_TASKS:
        raise DefinitionError()
    result = WorkflowDefinition(value["id"], tuple(nodes))
    if len(canonical_json(result.snapshot()).encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise DefinitionError()
    return result


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: _UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False) -> Any:
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise DefinitionError()
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_definition(source: Path | bytes | str) -> WorkflowDefinition:
    """Path loads are operator-owned files; strings are literal YAML, never paths."""
    try:
        if isinstance(source, Path):
            absolute = source.absolute()
            if (
                any(path.is_symlink() for path in (absolute, *absolute.parents))
                or not absolute.is_file()
            ):
                raise DefinitionError()
            with absolute.open("rb") as stream:
                raw = stream.read(MAX_DEFINITION_BYTES + 1)
        else:
            raw = source.encode("utf-8") if isinstance(source, str) else source
        if not isinstance(raw, bytes) or len(raw) > MAX_DEFINITION_BYTES or b"\x00" in raw:
            raise DefinitionError()
        text = raw.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (yaml.AliasToken, yaml.AnchorToken, yaml.TagToken)):
                raise DefinitionError()
        depth = 0
        for event in yaml.parse(text):
            if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
                depth += 1
            elif isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
                depth -= 1
            if depth > 16:
                raise DefinitionError()
        return parse_definition(yaml.load(text, Loader=_UniqueSafeLoader))
    except (OSError, UnicodeError, yaml.YAMLError, TypeError, ValueError, RecursionError):
        raise DefinitionError() from None
