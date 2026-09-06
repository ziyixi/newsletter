"""Internal state/result views, not a second public message schema.

Protobuf and contracts.py remain authoritative at every external boundary.
Payload deliberately marks normalized, dynamically shaped ProtoJSON (drafts,
packets and provider payloads). The small views below constrain the control flow
and results our own code constructs; they perform no additional serialization.
"""

from typing import Any, Literal, NotRequired, TypedDict

from .usage import UsageSummary

Payload = dict[str, Any]
EditionState = Literal["queued", "running", "ready", "blocked", "failed"]
DeliveryState = Literal[
    "not_requested", "submitting", "simulated", "provider_accepted", "rejected", "unknown"
]
ProjectionState = Literal["pending", "submitting", "done", "failed", "unknown"]
DigestState = Literal["current", "empty", "unavailable", "disabled"]
Role = Literal["ingest", "editor", "send"]


class ReviewResult(TypedDict):
    passed: bool
    findings: list[str]


class RenderResult(TypedDict):
    html: str
    text: str
    chart_png: str
    render_hash: str


class DeliveryResult(TypedDict):
    delivery_state: Literal["simulated", "provider_accepted"]
    provider_message_id: str


class PersonalItem(TypedDict):
    rank: int
    title: str
    detail: str


class EditionPatch(TypedDict, total=False):
    state: EditionState
    delivery_state: DeliveryState
    draft: Payload
    review: ReviewResult
    rendered: RenderResult
    personal_digest: Payload
    error_code: str
    provider_message_id: str
    usage: UsageSummary
    publication: Payload


class EditionRecord(TypedDict):
    id: str
    issue_date: str
    state: EditionState
    packet_ids: list[str]
    delivery_state: DeliveryState
    created_at: str
    updated_at: str
    is_fixture: bool
    draft: NotRequired[Payload]
    review: NotRequired[ReviewResult]
    rendered: NotRequired[RenderResult]
    personal_digest: NotRequired[Payload]
    error_code: NotRequired[str]
    provider_message_id: NotRequired[str]
    usage: NotRequired[UsageSummary]
    publication: NotRequired[Payload]
