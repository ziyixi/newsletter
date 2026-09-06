"""Opt-in local prompt trials; no service database, Notion, email or retries.

Run with the repository's locked Python environment. Inputs and raw outputs stay
in a new private directory outside any Git checkout and all Codex auth homes.
Validation measures shape/provenance boundaries, not factual or editorial quality.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import importlib.metadata
import math
import os
import platform
import re
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.contracts import (
    IDENTIFIER_PATTERN,
    canonical_json,
    content_hash,
    parse_message,
    validate_issue_date,
    validate_packet_body,
    validate_public_url,
)
from newsletter.editor import CodexEditor
from newsletter.errors import EditorError
from newsletter.model_io import MAX_JSON_BYTES, load_json
from newsletter.schema_compat import validate_output_schema
from newsletter.usage import UsageRecord, summarize_usage, usage_scope
from newsletter.workflow.content import parse_discovery, parse_plan
from newsletter.workflow.story_editor import _validate_content

REPOSITORY = Path(__file__).resolve().parents[1]
BODY_FIELDS = {"story_id", "title", "kind", "paragraphs", "limitations"}
STOP_ERRORS = {"authentication", "configuration", "rate_limit", "cancelled", "artifact_error"}
MAX_CASES = 40
RUNNER_VERSION = 1


class EvaluationError(ValueError):
    """Only fixed codes may leave the private artifact directory."""


def _identifier(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(IDENTIFIER_PATTERN, value) is not None


def validate_suite(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("cases"), list):
        raise EvaluationError("invalid_suite")
    if not 1 <= len(value["cases"]) <= MAX_CASES:
        raise EvaluationError("invalid_suite")
    ids = set()
    for case in value["cases"]:
        if (
            not isinstance(case, dict)
            or not {"id", "kind", "prompt", "instructions", "schema", "validation"} <= case.keys()
            or case.keys()
            - {"id", "kind", "prompt", "instructions", "schema", "validation", "allow_web"}
            or not _identifier(case["id"])
            or case["id"] in ids
            or case["kind"] not in {"selection", "summary", "discovery"}
            or not isinstance(case["prompt"], dict)
            or not isinstance(case["schema"], dict)
            or not isinstance(case["instructions"], str)
            or not case["instructions"].strip()
            or len(case["instructions"].encode()) > 100_000
            or len(canonical_json(case["prompt"]).encode()) > MAX_JSON_BYTES
            or type(case.get("allow_web", False)) is not bool
        ):
            raise EvaluationError("invalid_suite")
        ids.add(case["id"])
        validate_output_schema(case["schema"])
        validation = case["validation"]
        if not isinstance(validation, dict):
            raise EvaluationError("invalid_suite")
        if case["kind"] == "selection":
            if set(validation) != {"candidate_ids", "source_urls", "max_tasks"}:
                raise EvaluationError("invalid_suite")
            candidate_ids, urls = validation["candidate_ids"], validation["source_urls"]
            if (
                not isinstance(candidate_ids, list)
                or len(candidate_ids) > 60
                or any(not _identifier(item) for item in candidate_ids)
                or len(set(candidate_ids)) != len(candidate_ids)
                or not isinstance(urls, list)
                or len(urls) > 120
                or any(not isinstance(url, str) for url in urls)
                or len(set(urls)) != len(urls)
                or type(validation["max_tasks"]) is not int
                or not 1 <= validation["max_tasks"] <= 12
            ):
                raise EvaluationError("invalid_suite")
            for url in urls:
                validate_public_url(url)
        elif case["kind"] == "discovery":
            if set(validation) != {"direction", "issue_date", "seeds", "history"}:
                raise EvaluationError("invalid_suite")
            if (
                not _identifier(validation["direction"])
                or not isinstance(validation["seeds"], list)
                or len(validation["seeds"]) > 20
                or not isinstance(validation["history"], list)
                or len(validation["history"]) > 100
                or any(
                    not isinstance(item, dict)
                    for item in validation["seeds"] + validation["history"]
                )
            ):
                raise EvaluationError("invalid_suite")
            validate_issue_date(validation["issue_date"])
        else:
            if set(validation) != {"story_id", "packets", "paragraph_limit"}:
                raise EvaluationError("invalid_suite")
            if (
                not _identifier(validation["story_id"])
                or type(validation["paragraph_limit"]) is not int
                or not 1 <= validation["paragraph_limit"] <= 16
                or not isinstance(validation["packets"], list)
                or not 1 <= len(validation["packets"]) <= 60
            ):
                raise EvaluationError("invalid_suite")
            packet_ids = set()
            for packet in validation["packets"]:
                parse_message(packet, pb.Packet)
                validate_packet_body(packet["content"])
                if (
                    not _identifier(packet["id"])
                    or packet["id"] in packet_ids
                    or packet["content_hash"] != content_hash(packet["content"])
                ):
                    raise EvaluationError("invalid_suite")
                packet_ids.add(packet["id"])
    return deepcopy(value)


def _absolute(path: Path) -> Path:
    path = path.absolute()
    if ".." in path.parts or any(parent.is_symlink() for parent in (path, *path.parents)):
        raise EvaluationError("unsafe_path")
    return path


def private_output(output: Path, codex_home: Path) -> tuple[Path, Path]:
    output, codex_home = _absolute(output), _absolute(codex_home)
    user_home = Path.home().resolve()
    if (
        output.exists()
        or not output.parent.is_dir()
        or not codex_home.is_dir()
        or codex_home == user_home / ".codex"
        or output.is_relative_to(codex_home)
        or output.is_relative_to(user_home / ".codex")
        or output.is_relative_to(user_home / "Library" / "CloudStorage")
        or output.is_relative_to(user_home / "Library" / "Mobile Documents")
        or output.is_relative_to(REPOSITORY)
        or any((parent / ".git").exists() for parent in output.parents)
        or any(parent.name in {".codex", "codex-auth", ".codex-auth"} for parent in output.parents)
    ):
        raise EvaluationError("unsafe_path")
    output.mkdir(mode=0o700, exist_ok=False)
    return output, codex_home


def _write(path: Path, text: str, *, append: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if append else os.O_EXCL)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(text)
        target.flush()
        os.fsync(target.fileno())


def _json(path: Path, value: Any, *, append: bool = False) -> None:
    _write(path, canonical_json(value) + "\n", append=append)


def _versions() -> dict[str, Any]:
    packages = {}
    for name in ("personal-newsletter", "openai-codex", "ziyixi-protos"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not_installed"
    paths = [
        "scripts/evaluate_prompts.py",
        "src/newsletter/editor.py",
        "src/newsletter/usage.py",
        "src/newsletter/workflow/content.py",
        "src/newsletter/workflow/story_editor.py",
        "src/newsletter/schema_compat.py",
        "src/newsletter/codex_runtime.py",
    ]
    return {
        "runner": RUNNER_VERSION,
        "python": platform.python_version(),
        "packages": packages,
        "code_sha256": {
            name: hashlib.sha256((REPOSITORY / name).read_bytes()).hexdigest() for name in paths
        },
    }


def _validate_output(text: str, case: dict[str, Any], opened: set[str], searched: bool) -> Any:
    validation = case["validation"]
    if case["kind"] == "selection":
        return asdict(
            parse_plan(
                text,
                set(validation["candidate_ids"]),
                set(validation["source_urls"]),
                validation["max_tasks"],
            )
        )
    if case["kind"] == "discovery":
        return asdict(
            parse_discovery(
                text,
                opened,
                searched,
                validation["direction"],
                validation["issue_date"],
                seeds=validation["seeds"],
                history=validation["history"],
            )
        )
    value = load_json(text)
    if not isinstance(value, dict) or set(value) != BODY_FIELDS:
        raise EditorError("invalid_output")
    return _validate_content(
        value, validation["packets"], validation["story_id"], validation["paragraph_limit"]
    )


async def evaluate(
    suite: dict[str, Any],
    *,
    output: Path,
    codex_home: Path,
    allow_model_calls: bool,
    model: str = "gpt-5.6-sol",
    timeout: float = 300,
    editor_factory: Callable[..., CodexEditor] = CodexEditor,
    progress: Callable[[str], None] = print,
) -> dict[str, Any]:
    if not allow_model_calls:
        raise EvaluationError("model_calls_not_authorized")
    if (
        not isinstance(model, str)
        or not model.strip()
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise EvaluationError("invalid_configuration")
    suite = validate_suite(suite)
    output, codex_home = private_output(output, codex_home)
    _json(output / "suite.json", suite)
    _json(
        output / "manifest.json",
        {
            "input_hash": content_hash(suite),
            "model": model,
            "timeout_seconds": timeout,
            "versions": _versions(),
            "started_at": datetime.now(UTC).isoformat(),
            "limitations": "Structural validation and observed tool actions only; not quality or factual "
            "scoring and never authorization to publish. No runner retries. Production execute may "
            "perform one bounded provenance correction; observed turns are recorded explicitly.",
        },
    )
    prepared = []
    for index, case in enumerate(suite["cases"], 1):
        directory = output / f"case-{index:03d}"
        directory.mkdir(mode=0o700)
        workspace = directory / "workspace"
        workspace.mkdir(mode=0o700)
        _json(
            directory / "input.json",
            {
                **case,
                "input_hash": content_hash(case),
                "actual_prompt": canonical_json(case["prompt"]),
                "allow_web": case.get("allow_web", False),
            },
        )
        prepared.append((case, directory, workspace))
    results = []
    all_records: dict[str, UsageRecord] = {}
    stopped = None
    for index, (case, directory, workspace) in enumerate(prepared, 1):
        records: dict[str, UsageRecord] = {}
        outcome = {
            "id": case["id"],
            "input_hash": content_hash(case),
            "status": "skipped",
            "error_code": stopped,
            "elapsed_seconds": 0.0,
            "raw_output_available": False,
            "web_observation": {"searched": None, "opened_urls": None},
        }
        start = time.monotonic()

        def observe(record: UsageRecord) -> None:
            _json(directory / "usage-events.jsonl", record, append=True)
            records[record["id"]] = deepcopy(record)

        if stopped is None:
            progress(f"case {index}/{len(prepared)}: starting")
            # Capture SDK/Python diagnostics privately as well; never echo vendor
            # text, source URLs, raw answers, suite content or auth paths.
            descriptor = os.open(
                directory / "diagnostics.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as diagnostics:
                with (
                    contextlib.redirect_stdout(diagnostics),
                    contextlib.redirect_stderr(diagnostics),
                ):
                    try:
                        editor = editor_factory(codex_home, model, timeout_seconds=timeout)
                        with usage_scope(observe, f"evaluation:{index}"):
                            async with asyncio.timeout(timeout):
                                text, opened, searched = await editor.execute(
                                    canonical_json(case["prompt"]),
                                    deepcopy(case["schema"]),
                                    case["instructions"],
                                    workspace,
                                )
                        _write(directory / "raw-output.txt", text)
                        outcome["raw_output_available"] = True
                        outcome["web_observation"] = {
                            "searched": searched,
                            "opened_urls": sorted(opened),
                        }
                        if not case.get("allow_web", False) and (opened or searched):
                            outcome.update(
                                status="observation_failure", error_code="unexpected_web"
                            )
                        else:
                            _json(
                                directory / "validated.json",
                                _validate_output(text, case, opened, searched),
                            )
                            outcome.update(status="valid", error_code=None)
                    except asyncio.CancelledError:
                        outcome.update(status="failed", error_code="cancelled")
                    except TimeoutError:
                        outcome.update(status="failed", error_code="timeout")
                    except EditorError as error:
                        outcome.update(status="failed", error_code=error.code)
                    except OSError:
                        outcome.update(status="failed", error_code="artifact_error")
                    except (ValueError, TypeError, KeyError, AttributeError):
                        outcome.update(status="failed", error_code="invalid_output")
                    except Exception:
                        outcome.update(status="failed", error_code="unavailable")
            outcome["elapsed_seconds"] = round(time.monotonic() - start, 6)
            if outcome["error_code"] in STOP_ERRORS:
                stopped = outcome["error_code"]
        outcome["usage_records"] = list(records.values())
        outcome["usage"] = summarize_usage(list(records.values()))
        outcome["correction_observed"] = any(
            record["turns_started"] > 1 for record in records.values()
        )
        _json(directory / "result.json", outcome)
        all_records.update(records)
        results.append(outcome)
        counts = outcome["usage"]["usage"]
        tokens = counts["total_tokens"] if counts else "unknown"
        progress(
            f"case {index}/{len(prepared)}: {outcome['status']} tokens={tokens} partial={outcome['usage']['partial']}"
        )
    summary = {
        "input_hash": content_hash(suite),
        "cases": results,
        "usage": summarize_usage(list(all_records.values())),
        "stopped_reason": stopped,
        "completed_at": datetime.now(UTC).isoformat(),
        "all_structurally_valid": all(item["status"] == "valid" for item in results),
    }
    _json(output / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--allow-model-calls", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_model_calls:
        parser.error("Explicit --allow-model-calls is required; this uses model allowance.")
    try:
        path = _absolute(args.suite)
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            raise EvaluationError("invalid_suite")
        suite = load_json(path.read_text(encoding="utf-8"))
        result = asyncio.run(
            evaluate(
                suite,
                output=args.output,
                codex_home=args.codex_home,
                allow_model_calls=args.allow_model_calls,
                model=args.model,
                timeout=args.timeout,
            )
        )
        return 0 if result["all_structurally_valid"] else 1
    except EvaluationError:
        print("Evaluation refused: invalid suite, configuration or output location.")
    except (EditorError, OSError, ValueError, TypeError, KeyError, RecursionError):
        print("Evaluation failed safely; no issue or email was created.")
    except KeyboardInterrupt:
        print("Evaluation interrupted; no issue or email was created.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
