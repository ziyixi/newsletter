"""Prove the internal annotations reject unsafe state/result edits offline."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_types(source: str, cache: Path) -> subprocess.CompletedProcess[str]:
    case = cache.with_suffix(".py")
    case.write_text(source, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(ROOT / "pyproject.toml"),
            "--cache-dir",
            str(cache),
            "--no-incremental",
            str(ROOT / "src/newsletter"),
            str(case),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_internal_state_and_result_types_accept_real_boundaries(tmp_path):
    result = check_types(
        """
from newsletter.adapters import MailAdapter
from newsletter.store import Store
from newsletter.types import DeliveryResult, EditionRecord, RenderResult, ReviewResult

def update(store: Store, rendered: RenderResult, review: ReviewResult) -> EditionRecord:
    store.projection_result("packet", "unknown")
    return store.finish("edition", state="ready", rendered=rendered, review=review)

async def dispatch(mail: MailAdapter, edition: EditionRecord) -> DeliveryResult:
    return await mail.send(edition, "stable-key")
""",
        tmp_path / "valid-cache",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_internal_types_reject_misspelled_states_and_unfrozen_results(tmp_path):
    result = check_types(
        """
from newsletter.store import Store
from newsletter.types import DeliveryResult, RenderResult

def invalid(store: Store) -> None:
    store.finish("edition", state="sent")
    store.finish("edition", delivery_state="delivered")
    store.projection_result("packet", "retry")

delivery: DeliveryResult = {"delivery_state": "delivered", "provider_message_id": "id"}
rendered: RenderResult = {"html": "body", "text": "body", "chart_png": ""}
""",
        tmp_path / "invalid-cache",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.count("[arg-type]") == 3, result.stdout
    assert result.stdout.count("[typeddict-item]") == 2, result.stdout
    assert "render_hash" in result.stdout
