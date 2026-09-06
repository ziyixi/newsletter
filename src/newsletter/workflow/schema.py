"""Small discovery/planning envelopes; published material still uses protobuf."""

from newsletter.contracts import IDENTIFIER_PATTERN, SOURCE_ACCESS_SCOPES
from newsletter.types import Payload

CANDIDATE_FIELDS = (
    "title",
    "url",
    "doi",
    "version",
    "event_key",
    "published_at",
    "summary",
    "why_now",
    "access_scope",
)
TASK_FIELDS = (
    "id",
    "candidate_ids",
    "question",
    "why",
    "priority",
    "evidence_context",
    "source_urls",
)


def object_schema(properties: Payload) -> Payload:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


def discovery_schema(max_candidates: int = 5) -> Payload:
    props: Payload = {key: {"type": "string"} for key in CANDIDATE_FIELDS}
    props["access_scope"]["enum"] = list(SOURCE_ACCESS_SCOPES)
    props["summary"]["maxLength"] = 1200
    props["why_now"]["maxLength"] = 1000
    return object_schema(
        {
            "candidates": {
                "type": "array",
                "maxItems": max_candidates,
                "items": object_schema(props),
            },
            "note": {"type": "string", "maxLength": 2000},
        }
    )


def planning_schema(
    candidate_ids: list[str], source_urls: list[str], max_tasks: int, *, gaps: bool = False
) -> Payload:
    def choices(values: list[str], minimum: int, maximum: int) -> Payload:
        return {
            "type": "array",
            "minItems": minimum,
            "maxItems": maximum if values else 0,
            "items": {"type": "string", **({"enum": values} if values else {})},
        }

    task = object_schema(
        {
            "id": {"type": "string", "pattern": f"^{IDENTIFIER_PATTERN}$"},
            "candidate_ids": choices(candidate_ids, 0 if gaps else 1, 4),
            "question": {"type": "string", "maxLength": 1600},
            "why": {"type": "string", "maxLength": 1000},
            "priority": {"type": "integer", "minimum": 1, "maximum": max_tasks},
            "evidence_context": {"type": "string", "maxLength": 4000},
            "source_urls": choices(source_urls, 0, 8),
        }
    )
    return object_schema(
        {
            "research_tasks": {"type": "array", "maxItems": max_tasks, "items": task},
            "note": {"type": "string", "maxLength": 2000},
        }
    )
