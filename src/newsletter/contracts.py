"""Strict ProtoJSON and local shape/reference checks, not fact verification.

The public protobuf is the only message-shape definition. Validators constrain
resource use, URLs, dates, numbers and citations; they do not certify sources or
the truth of an article. URL checks do not perform DNS or network requests.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn, TypeVar, cast
from urllib.parse import unquote, urlsplit

from google.protobuf import json_format
from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.message import Message
from ziyixi_protos.newsletter import editorial_pb2 as pb

M = TypeVar("M", bound=Message)
MAX_MESSAGE_BYTES = 8 * 1024 * 1024
MAX_PACKET_BYTES = 1024 * 1024
MAX_PACKETS = 32
MAX_SOURCES = 32
MAX_CHART_POINTS = 32
# Ordered immutable values shared with the editor's structured-output schema.
SOURCE_ACCESS_SCOPES = ("metadata", "abstract", "full_text", "dataset")
SECTION_KINDS = ("world", "feature", "context")
CHART_KINDS = ("bar", "line")
IDENTIFIER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"
_IDENTIFIER = re.compile(IDENTIFIER_PATTERN + r"\Z")
_DECIMAL = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class ContractError(ValueError):
    """Safe caller-facing validation error; contains no upstream payload."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _fail(code: str, message: str) -> NoReturn:
    raise ContractError(code, message)


def to_dict(message: Message) -> dict[str, Any]:
    """ProtoJSON with snake_case names and explicit non-presence scalar defaults."""
    return json_format.MessageToDict(
        message,
        preserving_proto_field_name=True,
        always_print_fields_with_no_presence=True,
    )


def canonical_json(value: Any) -> str:
    """Canonical application JSON, not canonical protobuf wire serialization."""
    if isinstance(value, Message):
        value = to_dict(value)
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ContractError("INVALID_JSON", "Value is not finite JSON data") from exc


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("INVALID_JSON", "Duplicate JSON fields are not allowed")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    _fail("INVALID_JSON", "Non-finite JSON numbers are not allowed")


def _check_names(data: Any, descriptor: Descriptor, depth: int = 0) -> None:
    if depth > 32 or not isinstance(data, Mapping):
        _fail("INVALID_ARGUMENT", "A message must be a bounded JSON object")
    for name, value in data.items():
        field = descriptor.fields_by_name.get(name)
        if field is None:
            _fail("INVALID_ARGUMENT", f"Unknown or non-snake_case field in {descriptor.name}")
        if field.type != FieldDescriptor.TYPE_MESSAGE or value is None:
            continue
        if field.is_repeated:
            if not isinstance(value, list):
                _fail("INVALID_ARGUMENT", f"{name} must be a JSON array")
            for item in value:
                _check_names(item, cast(Descriptor, field.message_type), depth + 1)
        else:
            _check_names(value, cast(Descriptor, field.message_type), depth + 1)


def parse_message(data: Mapping[str, Any] | str | bytes, message_type: type[M]) -> M:
    """Parse only declared snake_case fields; semantic checks are explicit below."""
    try:
        if isinstance(data, (str, bytes)):
            if len(data.encode("utf-8") if isinstance(data, str) else data) > MAX_MESSAGE_BYTES:
                _fail("TOO_LARGE", "Message exceeds the byte limit")
            data = json.loads(
                data, object_pairs_hook=_unique_object, parse_constant=_reject_constant
            )
        _check_names(data, cast(Descriptor, message_type.DESCRIPTOR))
        if len(canonical_json(data).encode("utf-8")) > MAX_MESSAGE_BYTES:
            _fail("TOO_LARGE", "Message exceeds the byte limit")
        return json_format.ParseDict(
            dict(cast(Mapping[str, Any], data)), message_type(), ignore_unknown_fields=False
        )
    except ContractError:
        raise
    except (
        json.JSONDecodeError,
        UnicodeError,
        TypeError,
        ValueError,
        RecursionError,
        json_format.ParseError,
    ) as exc:
        raise ContractError("INVALID_ARGUMENT", "Invalid ProtoJSON message") from exc


def _coerce(value: Mapping[str, Any] | Message, message_type: type[M]) -> M:
    if isinstance(value, message_type):
        return value
    if isinstance(value, Message):
        _fail("INVALID_ARGUMENT", f"Expected {message_type.DESCRIPTOR.name}")
    return parse_message(value, message_type)


def _text(
    value: str, name: str, maximum: int, *, required: bool = True, single_line: bool = False
) -> None:
    if required and not value.strip():
        _fail("INVALID_ARGUMENT", f"{name} is required")
    if len(value) > maximum:
        _fail("TOO_LARGE", f"{name} exceeds its length limit")
    if any((ord(char) < 32 and char not in "\t\n\r") or ord(char) == 127 for char in value):
        _fail("INVALID_ARGUMENT", f"{name} contains control characters")
    if single_line and any(char in value for char in "\r\n\t"):
        _fail("INVALID_ARGUMENT", f"{name} must be a single line")


def _identifier(value: str, name: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        _fail("INVALID_ARGUMENT", f"{name} is not a valid identifier")


def _request_key(value: str) -> None:
    _text(value, "request_key", 128, single_line=True)
    if value != value.strip():
        _fail("INVALID_ARGUMENT", "request_key must not have surrounding whitespace")


def validate_issue_date(value: str) -> None:
    try:
        valid = (
            bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
            and date.fromisoformat(value).isoformat() == value
        )
    except ValueError:
        valid = False
    if not valid:
        _fail("INVALID_ARGUMENT", "issue_date must be a valid YYYY-MM-DD date")


def validate_public_url(value: str) -> None:
    """Reject unsafe URL syntax and literal/local hosts, without resolving DNS.

    Any future network fetcher must additionally validate resolved connection IPs
    and every redirect; accepting a domain here is not an SSRF-safe fetch permit.
    """
    try:
        if len(value) > 2048 or not value or value != value.strip():
            raise ValueError
        if "\\" in value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
            raise ValueError
        if any(ord(c) < 32 or ord(c) == 127 for c in unquote(value)):
            raise ValueError
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError
        host = parsed.hostname
        if not host or parsed.port not in {None, 80, 443}:
            raise ValueError
        host = host.rstrip(".").lower()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            ascii_host = host.encode("idna").decode("ascii")
            numeric_host = all(
                re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", label) for label in ascii_host.split(".")
            )
            if len(ascii_host) > 253 or "." not in ascii_host or numeric_host:
                raise ValueError
            if ascii_host.endswith(
                (".localhost", ".local", ".internal", ".home.arpa", ".localdomain")
            ):
                raise ValueError
            if not all(_HOST_LABEL.fullmatch(label) for label in ascii_host.split(".")):
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
    except (TypeError, ValueError, UnicodeError, AttributeError) as exc:
        raise ContractError("INVALID_URL", "Source URL must use a public HTTP(S) host") from exc


def validate_packet_body(body: Mapping[str, Any] | Message) -> None:
    packet = _coerce(body, pb.PacketBody)
    if packet.ByteSize() > MAX_PACKET_BYTES:
        _fail("TOO_LARGE", "Packet exceeds the byte limit")
    _text(packet.title, "packet.title", 300, single_line=True)
    _text(packet.body, "packet.body", 65536)
    if not 1 <= len(packet.sources) <= MAX_SOURCES:
        _fail("INVALID_ARGUMENT", f"Packet needs 1..{MAX_SOURCES} sources")
    seen: set[str] = set()
    for source in packet.sources:
        _identifier(source.id, "source.id")
        if source.id in seen:
            _fail("INVALID_ARGUMENT", "Source IDs must be unique within a packet")
        seen.add(source.id)
        _text(source.title, "source.title", 500, single_line=True)
        validate_public_url(source.url)
        _text(source.excerpt, "source.excerpt", 20000, required=False)
        if source.access_scope not in SOURCE_ACCESS_SCOPES:
            _fail("INVALID_ARGUMENT", "Unsupported source access_scope")
        if source.published_at:
            try:
                if len(source.published_at) > 40:
                    raise ValueError
                datetime.fromisoformat(source.published_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ContractError("INVALID_ARGUMENT", "Invalid source published_at") from exc
    if len(packet.tags) > 32:
        _fail("TOO_LARGE", "Too many packet tags")
    for tag in packet.tags:
        _text(tag, "tag", 64, single_line=True)


def _citations(values: Sequence[str], known: set[str]) -> None:
    if len(values) > 32:
        _fail("TOO_LARGE", "Too many citations in one element")
    if len(set(values)) != len(values):
        _fail("INVALID_CITATION", "Duplicate citations in one element")
    for value in values:
        if value not in known:
            _fail("INVALID_CITATION", "Citation does not identify an available packet/source")


def validate_decimal(value: str) -> Decimal:
    if len(value) > 64 or not _DECIMAL.fullmatch(value):
        _fail("INVALID_NUMBER", "Chart values must be finite decimal strings")
    try:
        number = Decimal(value)
        if not number.is_finite() or (number and abs(number.adjusted()) > 100):
            raise InvalidOperation
    except InvalidOperation as exc:
        raise ContractError(
            "INVALID_NUMBER", "Chart value is outside supported finite range"
        ) from exc
    return number


def validate_draft(
    draft: Mapping[str, Any] | Message, packets: Sequence[Mapping[str, Any] | Message]
) -> None:
    article = _coerce(draft, pb.Draft)
    if not 1 <= len(packets) <= MAX_PACKETS:
        _fail("INVALID_ARGUMENT", f"Draft requires 1..{MAX_PACKETS} packets")
    known: set[str] = set()
    packet_ids: set[str] = set()
    for value in packets:
        packet = _coerce(value, pb.Packet)
        _identifier(packet.id, "packet.id")
        if packet.id in packet_ids:
            _fail("INVALID_ARGUMENT", "Duplicate packet IDs")
        packet_ids.add(packet.id)
        validate_packet_body(packet.content)
        known.update(f"{packet.id}/{source.id}" for source in packet.content.sources)
    _text(article.subject, "subject", 200, single_line=True)
    _text(article.title, "title", 300, single_line=True)
    _text(article.introduction, "introduction", 4000, required=False)
    _text(article.limitations, "limitations", 8000, required=False)
    if not 1 <= len(article.sections) <= 4:
        _fail("INVALID_ARGUMENT", "Draft needs 1..4 sections")
    for section in article.sections:
        if section.kind not in SECTION_KINDS:
            _fail("INVALID_ARGUMENT", "Unsupported section kind")
        _text(section.heading, "section.heading", 300, single_line=True)
        _text(section.limitations, "section.limitations", 4000, required=False)
        if not 1 <= len(section.paragraphs) <= 16:
            _fail("INVALID_ARGUMENT", "Section needs 1..16 paragraphs")
        for paragraph in section.paragraphs:
            _text(paragraph.text, "paragraph.text", 8000)
            _citations(paragraph.citations, known)
    if article.HasField("chart"):
        chart = article.chart
        if chart.kind not in CHART_KINDS:
            _fail("INVALID_ARGUMENT", "Unsupported chart kind")
        for name in ("question", "metric", "unit", "period", "caption", "alt_text"):
            _text(getattr(chart, name), f"chart.{name}", 1000)
        _text(chart.limitations, "chart.limitations", 4000, required=False)
        if not 1 <= len(chart.points) <= MAX_CHART_POINTS:
            _fail("INVALID_ARGUMENT", "Invalid chart point count")
        has_value = False
        for point in chart.points:
            _text(point.label, "chart.point.label", 120, single_line=True)
            _citations(point.citations, known)
            if point.WhichOneof("observation") == "decimal_value":
                validate_decimal(point.decimal_value)
                if not point.citations:
                    _fail("INVALID_CITATION", "Numeric chart points require a citation")
                has_value = True
            elif point.WhichOneof("observation") == "missing_reason":
                _text(point.missing_reason, "missing_reason", 500)
            else:
                _fail("INVALID_NUMBER", "Chart point needs a value or a missing reason")
        if not has_value:
            _fail("INVALID_NUMBER", "A chart must contain a non-missing value")
    if article.HasField("recommended_reading"):
        _citations(
            [
                article.recommended_reading.citation,
                *article.recommended_reading.supporting_citations,
            ],
            known,
        )
        _text(article.recommended_reading.reason, "recommended_reading.reason", 1000)
    if article.ByteSize() > MAX_PACKET_BYTES:
        _fail("TOO_LARGE", "Draft exceeds the byte limit")


def validate_render_request(request: Mapping[str, Any] | Message) -> None:
    value = _coerce(request, pb.RenderEditionRequest)
    if value.ByteSize() > MAX_MESSAGE_BYTES:
        _fail("TOO_LARGE", "Render request exceeds the byte limit")
    validate_issue_date(value.issue_date)
    validate_draft(value.draft, value.packets)
    if value.HasField("personal_digest"):
        validate_personal_digest(value.personal_digest)


def validate_personal_digest(value: Mapping[str, Any] | Message) -> None:
    digest = _coerce(value, pb.PersonalDigest)
    if digest.state not in {"current", "empty", "unavailable", "disabled"}:
        _fail("INVALID_ARGUMENT", "Invalid personal digest state")
    _text(digest.title, "personal_digest.title", 200, single_line=True)
    _text(digest.summary, "personal_digest.summary", 12000, required=False)
    _text(
        digest.source_label, "personal_digest.source_label", 200, required=False, single_line=True
    )
    _text(digest.limitations, "personal_digest.limitations", 2000, required=False)
    _text(digest.error_code, "personal_digest.error_code", 100, required=False, single_line=True)
    if len(digest.items) > 10 or digest.time_window_hours > 168:
        _fail("INVALID_ARGUMENT", "Personal digest exceeds limits")
    seen = set()
    for item in digest.items:
        if not 1 <= item.rank <= 100 or item.rank in seen:
            _fail("INVALID_ARGUMENT", "Invalid or duplicate personal event rank")
        seen.add(item.rank)
        _text(item.title, "personal_event.title", 500, single_line=True)
        _text(item.detail, "personal_event.detail", 4000)
    if digest.state == "current" and not (digest.summary.strip() or digest.items):
        _fail("INVALID_ARGUMENT", "Current personal digest requires content")
    if digest.state != "current" and digest.items:
        _fail("INVALID_ARGUMENT", "Unavailable or empty personal digest cannot contain events")
    if digest.fetched_at:
        try:
            parsed = datetime.fromisoformat(digest.fetched_at.replace("Z", "+00:00"))
            if len(digest.fetched_at) > 40 or parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            _fail("INVALID_ARGUMENT", "Personal digest fetched_at must include timezone")


def validate_request(message: Message) -> None:
    """Validate public requests; does not perform authentication."""
    if isinstance(message, pb.StartRunRequest):
        _request_key(message.request_key)
        validate_issue_date(message.issue_date)
    elif isinstance(message, pb.GetRunRequest):
        _identifier(message.id, "run.id")
    elif isinstance(message, pb.PutPacketRequest):
        _request_key(message.request_key)
        _identifier(message.workflow_id, "workflow_id")
        validate_packet_body(message.content)
    elif isinstance(message, pb.ReadInboxRequest):
        if message.limit > 100:
            _fail("INVALID_ARGUMENT", "limit must be 0 (default) or 1..100")
        _text(message.cursor, "cursor", 2048, required=False, single_line=True)
    elif isinstance(message, pb.PrepareEditionRequest):
        _request_key(message.request_key)
        validate_issue_date(message.issue_date)
        if not 1 <= len(message.packet_ids) <= MAX_PACKETS:
            _fail("INVALID_ARGUMENT", f"Prepare requires 1..{MAX_PACKETS} packet IDs")
        if len(set(message.packet_ids)) != len(message.packet_ids):
            _fail("INVALID_ARGUMENT", "Duplicate packet IDs")
        for packet_id in message.packet_ids:
            _identifier(packet_id, "packet_id")
    elif isinstance(message, pb.GetEditionRequest):
        _identifier(message.id, "edition.id")
    elif isinstance(message, pb.RenderEditionRequest):
        validate_render_request(message)
    elif isinstance(message, pb.SendEditionRequest):
        _identifier(message.id, "edition.id")
        _request_key(message.request_key)
        if not _HASH.fullmatch(message.expected_render_hash):
            _fail("INVALID_ARGUMENT", "expected_render_hash must be a SHA-256 hex digest")
    else:
        _fail("INVALID_ARGUMENT", "Unsupported request message")


# Explicit spelling aliases for application/CLI consumers, not extra endpoints.
parse_proto = parse_message
dump_proto = to_dict
