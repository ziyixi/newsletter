"""Versioned editorial data, validated before activation and frozen per run.

No provider clients, secrets, database access, model calls or business operations
belong here. A bundle is bounded UTF-8 data for registered engine capabilities,
not a way to add Python, shell commands, recipients or permissions.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, cast

import yaml

from newsletter.collection.instructions import (
    MAX_INSTRUCTION_BYTES,
    Instruction,
)
from newsletter.contracts import canonical_json, content_hash
from newsletter.types import Payload
from newsletter.workflow.definition import WorkflowDefinition, load_definition

CONFIG_API = 1
MAX_BUNDLE_BYTES = 768_000
MAX_FILE_BYTES = 100_000
MAX_FILES = 24
REQUIRED_FILES = frozenset(
    {
        "editorial.yaml",
        "workflow.yaml",
        "policy/editorial.md",
        "policy/reader-profile.md",
        "prompts/discovery.md",
        "prompts/selection.md",
        "templates/edition.html.j2",
    }
)
EDITORIAL_KEYS = frozenset(
    {
        "max_public_items",
        "max_research_items",
        "max_deep",
        "max_research_candidates",
    }
)
DEFAULT_EDITORIAL = {
    "max_public_items": 6,
    "max_research_items": 1,
    "max_deep": 1,
    "max_research_candidates": 10,
}
_DIRECTION = re.compile(r"discovery/([a-z0-9][a-z0-9_-]{0,63})\.md\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"(?:[0-9a-f]{40}|packaged)\Z")


class ContentConfigError(ValueError):
    def __init__(self) -> None:
        super().__init__("CONTENT_CONFIG_INVALID")


def _editorial(text: str) -> dict[str, int]:
    if len(text.encode()) > 4096:
        raise ContentConfigError()
    for token in yaml.scan(text):
        if isinstance(
            token, (yaml.AliasToken, yaml.AnchorToken, yaml.TagToken)
        ):
            raise ContentConfigError()
    node = yaml.compose(text, Loader=yaml.SafeLoader)
    if not isinstance(node, yaml.MappingNode) or len(node.value) != len(
        EDITORIAL_KEYS
    ):
        raise ContentConfigError()
    keys = []
    for key, value in node.value:
        if not isinstance(key, yaml.ScalarNode) or not isinstance(
            value, yaml.ScalarNode
        ):
            raise ContentConfigError()
        keys.append(key.value)
    if len(set(keys)) != len(keys):
        raise ContentConfigError()
    result = yaml.safe_load(text)
    if not isinstance(result, dict) or set(result) != EDITORIAL_KEYS:
        raise ContentConfigError()
    if any(type(value) is not int for value in result.values()):
        raise ContentConfigError()
    if not (
        1 <= result["max_public_items"] <= 8
        and 0 <= result["max_research_items"] <= result["max_public_items"]
        and 0 <= result["max_deep"] <= min(2, result["max_public_items"])
        and 0 <= result["max_research_candidates"] <= 60
    ):
        raise ContentConfigError()
    return cast(dict[str, int], result)


def config_instructions(files: Mapping[str, str]) -> list[Instruction]:
    """Build instructions from the one in-memory bundle, never reread current."""
    result = []
    for name in sorted(files):
        match = _DIRECTION.fullmatch(name)
        if not match:
            continue
        identifier = match[1]
        text = files[name]
        if identifier == "01-ai-ml" and "discovery/_sources/ai-ml.md" in files:
            text += (
                "\n\n## Frozen public source guide\n\n"
                + files["discovery/_sources/ai-ml.md"]
            )
        if not text.strip() or len(text.encode()) > MAX_INSTRUCTION_BYTES:
            raise ContentConfigError()
        result.append(Instruction(identifier, text, content_hash(text)))
    if not 1 <= len(result) <= 8:
        raise ContentConfigError()
    return result


def config_definition(snapshot: Payload) -> WorkflowDefinition:
    return load_definition(snapshot["files"]["workflow.yaml"])


def _validate_files(files: object) -> tuple[dict[str, str], dict[str, int]]:
    if (
        not isinstance(files, dict)
        or not len(REQUIRED_FILES) < len(files) <= MAX_FILES
    ):
        raise ContentConfigError()
    if not REQUIRED_FILES <= files.keys():
        raise ContentConfigError()
    for name, value in files.items():
        if not isinstance(name, str) or not (
            name in REQUIRED_FILES
            or _DIRECTION.fullmatch(name)
            or name == "discovery/_sources/ai-ml.md"
        ):
            raise ContentConfigError()
        if (
            not isinstance(value, str)
            or not value.strip()
            or "\x00" in value
            or len(value.encode("utf-8")) > MAX_FILE_BYTES
        ):
            raise ContentConfigError()
    selected = cast(dict[str, str], files)
    editorial = _editorial(selected["editorial.yaml"])
    instructions = config_instructions(selected)
    definition = load_definition(selected["workflow.yaml"])
    # Lazy imports keep the pure snapshot layer out of handler import cycles.
    from newsletter.workflow.story_recipe import validate_story_recipe

    validate_story_recipe(definition)
    roles = {node.type: node for node in definition.nodes}
    if (
        editorial["max_research_candidates"]
        > roles["deduplicate"].params.get("max_candidates", 30)
        or editorial["max_public_items"]
        > roles["selection"].params.get("max_tasks", 8)
        or editorial["max_deep"] > roles["story_plan"].params.get("max_deep", 4)
    ):
        raise ContentConfigError()
    for node in definition.nodes:
        if node.type == "discovery" and (
            node.map is None or len(instructions) > node.map.max_items
        ):
            raise ContentConfigError()
    from newsletter.rendering import validate_template

    validate_template(selected["templates/edition.html.j2"])
    return selected, editorial


def build_snapshot(files: Mapping[str, str], revision: str) -> Payload:
    body: Payload = {
        "schema_version": CONFIG_API,
        "revision": revision,
        "files": dict(files),
    }
    body["digest"] = content_hash(body)
    try:
        body["editorial"] = _editorial(body["files"]["editorial.yaml"])
        return validate_snapshot(body)
    except (KeyError, TypeError, ValueError, yaml.YAMLError, RecursionError):
        raise ContentConfigError() from None


def validate_snapshot(value: object) -> Payload:
    """Check both integrity and engine compatibility; return an owned deep copy."""
    try:
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "revision",
            "digest",
            "files",
            "editorial",
        }:
            raise ContentConfigError()
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != CONFIG_API
        ):
            raise ContentConfigError()
        if not isinstance(value["revision"], str) or not _REVISION.fullmatch(
            value["revision"]
        ):
            raise ContentConfigError()
        if not isinstance(value["digest"], str) or not _DIGEST.fullmatch(
            value["digest"]
        ):
            raise ContentConfigError()
        encoded = canonical_json(value)
        if len(encoded.encode()) > MAX_BUNDLE_BYTES:
            raise ContentConfigError()
        expected = content_hash(
            {key: value[key] for key in ("schema_version", "revision", "files")}
        )
        if expected != value["digest"]:
            raise ContentConfigError()
        _, editorial = _validate_files(value["files"])
        if (
            not isinstance(value["editorial"], dict)
            or value["editorial"] != editorial
        ):
            raise ContentConfigError()
        if any(type(item) is not int for item in value["editorial"].values()):
            raise ContentConfigError()
        return cast(Payload, json.loads(encoded))
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        yaml.YAMLError,
        RecursionError,
        OverflowError,
    ):
        raise ContentConfigError() from None


def packaged_snapshot() -> Payload:
    """Explicit install baseline, never a hidden substitute for a broken active bundle."""
    from newsletter.workflow.content import (
        DEFAULT_DISCOVERY_POLICY,
        DEFAULT_SELECTION_POLICY,
    )

    package = Path(__file__).parent
    files = {
        "editorial.yaml": yaml.safe_dump(DEFAULT_EDITORIAL, sort_keys=False),
        "workflow.yaml": (package / "workflows/daily.yaml").read_text(),
        "policy/editorial.md": (
            package / "policy/story-editorial.md"
        ).read_text(),
        "policy/reader-profile.md": (
            package / "policy/reader-profile.md"
        ).read_text(),
        "prompts/discovery.md": DEFAULT_DISCOVERY_POLICY,
        "prompts/selection.md": DEFAULT_SELECTION_POLICY,
        "templates/edition.html.j2": (
            package / "templates/edition.html.j2"
        ).read_text(),
    }
    folder = package / "instructions/discovery"
    for path in sorted(folder.glob("*.md")):
        files["discovery/" + path.name] = path.read_text()
    guide = folder / "_sources/ai-ml.md"
    if guide.is_file():
        files["discovery/_sources/ai-ml.md"] = guide.read_text()
    return build_snapshot(files, "packaged")


def _real_directory(path: Path, *, create: bool = False) -> Path:
    path = path.absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ContentConfigError()
    if create:
        path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not path.is_dir():
        raise ContentConfigError()
    return path


def _read_json(path: Path, maximum: int = MAX_BUNDLE_BYTES) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ContentConfigError()
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ContentConfigError()

    # Duplicate JSON keys are never an alternative representation of a bundle.
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, item in items:
            if key in result:
                raise ContentConfigError()
            result[key] = item
        return result

    return json.loads(raw, object_pairs_hook=pairs)


def read_snapshot(path: Path) -> Payload:
    try:
        return validate_snapshot(_read_json(path))
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise ContentConfigError() from None


def load_active(root: Path) -> Payload:
    """Read the pointer once, then only the named immutable release."""
    try:
        root = _real_directory(root)
        active = _read_json(root / "active.json", 2048)
        if not isinstance(active, dict) or set(active) != {
            "revision",
            "digest",
        }:
            raise ContentConfigError()
        digest = active["digest"]
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ContentConfigError()
        release = _real_directory(_real_directory(root / "releases") / digest)
        snapshot = read_snapshot(release / "bundle.json")
        if any(active[key] != snapshot[key] for key in ("revision", "digest")):
            raise ContentConfigError()
        return snapshot
    except (OSError, KeyError, TypeError, ValueError, RecursionError):
        raise ContentConfigError() from None


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: Payload) -> None:
    if path.is_symlink():
        raise ContentConfigError()
    descriptor, temporary = tempfile.mkstemp(
        prefix=".config-write-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _install_lock(root: Path) -> Iterator[None]:
    lock = root / ".install.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ContentConfigError()
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def install_snapshot(root: Path, snapshot: Payload) -> None:
    """Validate in isolation; preserve the old pointer on any failure before commit."""
    checked = validate_snapshot(snapshot)
    root = _real_directory(root, create=True)
    with _install_lock(root):
        releases = _real_directory(root / "releases", create=True)
        destination = releases / checked["digest"]
        if destination.exists() or destination.is_symlink():
            release = _real_directory(destination)
            if read_snapshot(release / "bundle.json") != checked:
                raise ContentConfigError()
        else:
            with tempfile.TemporaryDirectory(
                prefix=".config-stage-", dir=releases
            ) as name:
                stage = Path(name)
                _atomic_json(stage / "bundle.json", checked)
                os.rename(stage, destination)
                _sync_directory(releases)
        pointer = {key: checked[key] for key in ("revision", "digest")}
        if (root / "active.json").exists() and _read_json(
            root / "active.json", 2048
        ) == pointer:
            return
        _atomic_json(root / "active.json", pointer)


def build_directory(folder: Path, revision: str) -> Payload:
    """Read authored configuration only; reject additional files and symlinks."""
    folder = _real_directory(folder)
    files: dict[str, str] = {}
    for path in folder.rglob("*"):
        if path.is_symlink():
            raise ContentConfigError()
        if path.is_dir():
            continue
        if not path.is_file() or len(files) >= MAX_FILES:
            raise ContentConfigError()
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ContentConfigError()
        files[path.relative_to(folder).as_posix()] = raw.decode("utf-8")
    return build_snapshot(files, revision)
