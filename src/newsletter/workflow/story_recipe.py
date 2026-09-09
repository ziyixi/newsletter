"""Strict topic-DAG topology; optional editorial parts cannot grant send authority."""

from newsletter.workflow.definition import (
    DefinitionError,
    NodeDefinition,
    WorkflowDefinition,
    parse_definition,
)

STORY_TYPES = frozenset({"story_plan", "story_brief", "story_deep", "publish"})


def is_story_recipe(definition: WorkflowDefinition) -> bool:
    # Partial or corrupt story graphs must not be mistaken for legacy recipes.
    return any(node.type in STORY_TYPES for node in definition.nodes)


def validate_story_recipe(definition: WorkflowDefinition) -> None:
    # Persisted or directly constructed dataclasses are not a syntax bypass.
    definition = parse_definition(definition.snapshot())
    by_id = {node.id: node for node in definition.nodes}
    required = {
        "history",
        "deduplicate",
        "selection",
        "story_plan",
        "story_brief",
        "story_deep",
        "publish",
    }
    allowed = required | {"api_feed", "discovery"}
    if any(node.type not in allowed for node in definition.nodes):
        raise DefinitionError()
    roles: dict[str, NodeDefinition] = {}
    for kind in required:
        nodes = [node for node in definition.nodes if node.type == kind]
        if len(nodes) != 1:
            raise DefinitionError()
        roles[kind] = nodes[0]
    discoveries = [
        node for node in definition.nodes if node.type == "discovery"
    ]
    feeds = [node for node in definition.nodes if node.type == "api_feed"]
    if not discoveries:
        raise DefinitionError()
    history = roles["history"]
    if history.needs or history.on_error != "stop":
        raise DefinitionError()
    for feed in feeds:
        if feed.map is not None or set(feed.needs) - {history.id}:
            raise DefinitionError()
    for discovery in discoveries:
        if (
            discovery.map is None
            or discovery.map.source != "run.instructions"
            or {history.id, *(node.id for node in feeds)} - set(discovery.needs)
        ):
            raise DefinitionError()
    if {history.id, *(node.id for node in feeds + discoveries)} - set(
        roles["deduplicate"].needs
    ):
        raise DefinitionError()
    requirements = {
        "deduplicate": {"history", "discovery"},
        "selection": {"history", "deduplicate"},
        "story_plan": {"history", "deduplicate", "selection"},
        "story_brief": {"history", "deduplicate", "story_plan"},
        "story_deep": {"history", "deduplicate", "story_plan", "story_brief"},
        "publish": {"story_plan", "story_brief", "story_deep"},
    }
    for kind, dependencies in requirements.items():
        if not dependencies <= {
            by_id[dependency].type for dependency in roles[kind].needs
        }:
            raise DefinitionError()
    for node in definition.nodes:
        if (
            node.type in {"api_feed", "discovery", "story_brief", "story_deep"}
            and node.on_error != "continue"
        ):
            raise DefinitionError()
        parameters = {"timeout_seconds"}
        parameters |= (
            {"max_candidates"} if node.type == "deduplicate" else set()
        )
        parameters |= {"max_tasks"} if node.type == "selection" else set()
        parameters |= {"max_deep"} if node.type == "story_plan" else set()
        if set(node.params) - parameters:
            raise DefinitionError()
        for key, value in node.params.items():
            bounds = {
                "timeout_seconds": (1, 900),
                "max_candidates": (1, 60),
                "max_tasks": (1, 12),
                "max_deep": (0, 4),
            }
            if (
                type(value) is not int
                or not bounds[key][0] <= value <= bounds[key][1]
            ):
                raise DefinitionError()
        if (
            node.type
            in {"story_plan", "publish", "history", "selection", "deduplicate"}
            and node.map is not None
        ):
            raise DefinitionError()
    for kind, field in (
        ("story_brief", "brief_tasks"),
        ("story_deep", "deep_tasks"),
    ):
        node = roles[kind]
        if (
            node.map is None
            or node.map.source != roles["story_plan"].id + "." + field
        ):
            raise DefinitionError()
    brief_map, deep_map = roles["story_brief"].map, roles["story_deep"].map
    if brief_map is None or deep_map is None:
        raise DefinitionError()
    if roles["selection"].params.get("max_tasks", 8) > brief_map.max_items:
        raise DefinitionError()
    if roles["story_plan"].params.get("max_deep", 4) > deep_map.max_items:
        raise DefinitionError()
    if brief_map.max_items > 12 or deep_map.max_items > 4:
        raise DefinitionError()
