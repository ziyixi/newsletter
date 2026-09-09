"""Opt-in real provider schema acceptance; never generate or publish an issue.

Unlike the offline startup smoke, this spends a small amount of model allowance.
It uses the configured dedicated login and production writer/reviewer schemas,
asks only for empty diagnostic envelopes, and never opens service storage.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from newsletter.contracts import canonical_json
from newsletter.editor import CodexEditor
from newsletter.errors import EditorError
from newsletter.settings import Settings
from newsletter.types import Payload
from newsletter.usage import UsageRecord, summarize_usage, usage_scope
from newsletter.workflow.story_editor import (
    COMPONENTS,
    story_review_schema,
    story_writer_schema,
)


def smoke_cases() -> list[tuple[str, Payload, Payload]]:
    empty: Payload = {
        "content": None,
        "signal": None,
        "supplemental_packets": [],
    }
    cases: list[tuple[str, Payload, Payload]] = [
        (
            "brief",
            story_writer_schema("brief", story_id="schema-acceptance"),
            empty,
        ),
        (
            "deep",
            story_writer_schema("deep", story_id="schema-acceptance"),
            empty,
        ),
        (
            "brief_repair",
            story_writer_schema(
                "brief", repair=True, story_id="schema-acceptance"
            ),
            empty,
        ),
    ]
    cases.append(
        (
            "review",
            story_review_schema(),
            {
                "prior_withdrawal": None,
                "assessments": [
                    {
                        "component": component,
                        "status": "not_present",
                        "findings": [],
                    }
                    for component in COMPONENTS
                ],
                "issues": [],
            },
        )
    )
    return cases


async def check_schemas(editor: CodexEditor) -> Payload:
    records: dict[str, UsageRecord] = {}
    checked = []
    for name, schema, expected in smoke_cases():
        with tempfile.TemporaryDirectory(
            prefix="newsletter-schema-smoke-"
        ) as temporary:
            with usage_scope(
                lambda record: records.__setitem__(record["id"], record), name
            ):
                text, opened, searched = await editor.execute(
                    "Schema compatibility diagnostic only. Return this exact empty envelope: "
                    + canonical_json(expected),
                    schema,
                    "This is a schema acceptance probe, not an editorial task. Do not use tools, "
                    "research, read files, or invent content. Return only the requested JSON.",
                    Path(temporary).resolve(),
                )
            try:
                accepted = (
                    json.loads(text) == expected and not opened and not searched
                )
            except (TypeError, ValueError):
                accepted = False
            if not accepted:
                raise EditorError("invalid_output")
            checked.append(name)
    return {
        "accepted": True,
        "schemas": checked,
        "usage": summarize_usage(list(records.values())),
        "limitations": "Schema acceptance only, not a research, fact-check, or delivery test.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model-calls", action="store_true")
    args = parser.parse_args()
    if not args.allow_model_calls:
        parser.error(
            "Explicit --allow-model-calls is required; this uses model allowance."
        )
    try:
        settings = Settings.from_env()
        if settings.codex_home is None or not settings.model.strip():
            raise EditorError("configuration")
        editor = CodexEditor(
            settings.codex_home, settings.model, timeout_seconds=90
        )
        print(canonical_json(asyncio.run(check_schemas(editor))))
    except EditorError as error:
        raise SystemExit(
            f"Schema acceptance failed: {error.code}; no issue or email created."
        ) from None
    except Exception:
        raise SystemExit(
            "Schema acceptance failed: configuration; no issue or email created."
        ) from None


if __name__ == "__main__":
    main()
