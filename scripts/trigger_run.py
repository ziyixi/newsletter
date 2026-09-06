"""Checkout-only compatibility wrapper; the production entrypoint is newsletter-trigger."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "src" / "newsletter" / "trigger.py"),
        run_name="__main__",
    )
