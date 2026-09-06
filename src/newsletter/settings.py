"""Explicit configuration; never implicitly load the legacy .env or model API keys."""

import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar
from zoneinfo import ZoneInfo

_Number = TypeVar("_Number", int, float)


def _number_env(name: str, default: str, parse: Callable[[str], _Number]) -> _Number:
    try:
        return parse(os.getenv(name, default))
    except ValueError:
        # Built-in numeric errors echo the input, which may be a misplaced key.
        # Suppress that exception's context even when startup prints a traceback.
        raise ValueError(f"Set a valid numeric value for {name}") from None


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(".data")
    mode: str = "mock"
    editor_backend: str = "mock"
    ingest_token: str = field(default="", repr=False)
    editor_token: str = field(default="", repr=False)
    send_token: str = field(default="", repr=False)
    time_zone: str = "America/Los_Angeles"
    job_timeout_seconds: float = 900
    max_body_bytes: int = 1_048_576
    max_packets: int = 20
    max_pending_jobs: int = 8
    notion_backend: str = "disabled"
    notion_token: str = field(default="", repr=False)
    notion_data_source_id: str = ""
    mail_backend: str = "fake"
    allow_send: bool = False
    resend_api_key: str = field(default="", repr=False)
    recipient_email: str = ""
    from_email: str = ""
    codex_home: Path | None = None
    model: str = "gpt-5.6-sol"
    todofy_backend: str = "disabled"
    todofy_base_url: str = "https://daily.ziyixi.science"
    todofy_user: str = field(default="", repr=False)
    todofy_password: str = field(default="", repr=False)
    todofy_mode: str = "recommendation"
    todofy_top: int = 5
    instructions_dir: Path = Path(__file__).parent / "instructions"
    collection_timeout_seconds: float = 600

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_dir=Path(os.getenv("NEWSLETTER_DATA_DIR", ".data")),
            mode=os.getenv("NEWSLETTER_MODE", "mock"),
            editor_backend=os.getenv("NEWSLETTER_EDITOR", "mock"),
            ingest_token=os.getenv("NEWSLETTER_INGEST_TOKEN", ""),
            editor_token=os.getenv("NEWSLETTER_EDITOR_TOKEN", ""),
            send_token=os.getenv("NEWSLETTER_SEND_TOKEN", ""),
            time_zone=os.getenv("NEWSLETTER_TIME_ZONE", "America/Los_Angeles"),
            job_timeout_seconds=_number_env("NEWSLETTER_JOB_TIMEOUT_SECONDS", "900", float),
            notion_backend=os.getenv("NEWSLETTER_NOTION", "disabled"),
            notion_token=os.getenv("NOTION_TOKEN", ""),
            notion_data_source_id=os.getenv("NOTION_DATA_SOURCE_ID", ""),
            mail_backend=os.getenv("NEWSLETTER_MAIL", "fake"),
            allow_send=os.getenv("NEWSLETTER_ALLOW_SEND", "false").lower() == "true",
            resend_api_key=os.getenv("RESEND_API_KEY", ""),
            recipient_email=os.getenv("RECIPIENT_EMAIL", ""),
            from_email=os.getenv("NEWSLETTER_FROM_EMAIL", ""),
            codex_home=Path(os.environ["NEWSLETTER_CODEX_HOME"])
            if os.getenv("NEWSLETTER_CODEX_HOME")
            else None,
            model=os.getenv("NEWSLETTER_MODEL", "gpt-5.6-sol"),
            todofy_backend=os.getenv("NEWSLETTER_TODOFY", "disabled"),
            todofy_base_url=os.getenv("TODO_API_BASE", "https://daily.ziyixi.science"),
            todofy_user=os.getenv("TODO_API_USER", ""),
            todofy_password=os.getenv("TODO_API_PASSWORD", ""),
            todofy_mode=os.getenv("NEWSLETTER_TODOFY_MODE", "recommendation"),
            todofy_top=_number_env("NEWSLETTER_TODOFY_TOP", "5", int),
            instructions_dir=Path(os.environ["NEWSLETTER_INSTRUCTIONS_DIR"])
            if os.getenv("NEWSLETTER_INSTRUCTIONS_DIR")
            else Path(__file__).parent / "instructions",
            collection_timeout_seconds=_number_env(
                "NEWSLETTER_COLLECTION_TIMEOUT_SECONDS", "600", float
            ),
        )

    def validate(self) -> None:
        if (
            not math.isfinite(self.collection_timeout_seconds)
            or not 0 < self.collection_timeout_seconds <= 1800
        ):
            raise ValueError("Collection timeout must be within 0..1800 seconds per direction")
        if self.todofy_backend not in {"disabled", "fake", "todofy"}:
            raise ValueError("NEWSLETTER_TODOFY must be disabled, fake or todofy")
        if self.todofy_mode not in {"recommendation", "summary"} or not 1 <= self.todofy_top <= 10:
            raise ValueError("Invalid Todofy mode or item limit")
        if self.todofy_backend == "todofy" and not (self.todofy_user and self.todofy_password):
            raise ValueError("Todofy requires TODO_API_USER and TODO_API_PASSWORD")
        if self.mode == "mock" and self.todofy_backend == "todofy":
            raise ValueError("Mock mode forbids real Todofy requests")
        if self.mode == "live" and self.todofy_backend == "fake":
            raise ValueError("Live mode forbids fake personal events")
        directory = self.data_dir.resolve()
        if directory in {Path(directory.anchor), Path.home().resolve(), Path.cwd().resolve()}:
            raise ValueError("Use a dedicated child directory for newsletter data")
        if self.data_dir.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError("Newsletter data must be a dedicated real directory")
        if self.mode not in {"mock", "live"}:
            raise ValueError("NEWSLETTER_MODE must be mock or live")
        if self.editor_backend not in {"mock", "codex"}:
            raise ValueError("NEWSLETTER_EDITOR must be mock or codex")
        if self.notion_backend not in {"disabled", "fake", "notion"}:
            raise ValueError("NEWSLETTER_NOTION must be disabled, fake or notion")
        if self.mail_backend not in {"fake", "resend"}:
            raise ValueError("NEWSLETTER_MAIL must be fake or resend")
        tokens = [self.ingest_token, self.editor_token, self.send_token]
        if (
            any(len(t) < 24 or len(t) > 512 or any(c.isspace() for c in t) for t in tokens)
            or len(set(tokens)) != 3
        ):
            raise ValueError("Configure three distinct NEWSLETTER_*_TOKEN values (24+ characters)")
        if self.mode == "mock" and (
            self.editor_backend != "mock"
            or self.mail_backend != "fake"
            or self.notion_backend == "notion"
        ):
            raise ValueError("Mock mode forbids real model, Notion, and mail adapters")
        if self.mode == "live" and self.editor_backend != "codex":
            raise ValueError("Live mode requires the Codex editor; no mock fallback")
        if self.editor_backend == "codex" and self.codex_home is None:
            raise ValueError("Set an isolated NEWSLETTER_CODEX_HOME for the server editor")
        if self.notion_backend == "notion" and (
            not self.notion_token or not self.notion_data_source_id
        ):
            raise ValueError("Notion requires NOTION_TOKEN and NOTION_DATA_SOURCE_ID")
        if self.mail_backend == "resend" and (
            not self.allow_send
            or not self.resend_api_key
            or not self.recipient_email
            or not self.from_email
        ):
            raise ValueError("Resend requires explicit send enablement, key, from and recipient")
        if not math.isfinite(self.job_timeout_seconds) or not 0 < self.job_timeout_seconds <= 3600:
            raise ValueError("Job timeout must be finite and within 0..3600 seconds")
        if not 1 <= self.max_packets <= 32 or not 1 <= self.max_pending_jobs <= 100:
            raise ValueError("Invalid packet or queue limits")
        if not 1024 <= self.max_body_bytes <= 8 * 1024 * 1024:
            raise ValueError("Invalid request body limit")
        ZoneInfo(self.time_zone)
