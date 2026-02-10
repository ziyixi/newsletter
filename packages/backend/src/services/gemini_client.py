"""
Shared Gemini client — retry, backoff, and rate-limiting.

Centralises all Gemini API access so callers don't duplicate
error-handling / fallback logic.
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..config import cfg

_FALLBACK_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

# Minimum gap between consecutive API calls (seconds)
_MIN_CALL_GAP = 1.0
_last_call_ts: float = 0.0

# Retry settings
_MAX_RETRIES = 2
_BACKOFF_BASE = 2.0  # seconds


def get_client() -> Any | None:
    """Return a ``genai.Client`` if the API key is set, else *None*."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        from google import genai  # type: ignore[import-untyped]

        return genai.Client(api_key=api_key)
    except ImportError:
        print("⚠️  google-genai not installed — Gemini features disabled")
        return None


def generate(
    client: Any,
    prompt: str,
    *,
    models: list[str] | None = None,
) -> str | None:
    """Call Gemini with automatic model fallback, retry, and rate-limiting.

    Returns the response text on success, or *None* if every attempt fails.
    """
    global _last_call_ts

    if models is None:
        models = [cfg.gemini_model, *_FALLBACK_MODELS]

    for model_name in models:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                # Simple rate-limit: space calls apart
                elapsed = time.monotonic() - _last_call_ts
                if elapsed < _MIN_CALL_GAP:
                    time.sleep(_MIN_CALL_GAP - elapsed)

                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                _last_call_ts = time.monotonic()

                if resp.text:
                    return resp.text.strip()
            except Exception as e:
                _last_call_ts = time.monotonic()
                wait = _BACKOFF_BASE ** attempt
                print(
                    f"⚠️  Gemini ({model_name}) attempt {attempt + 1} failed: {e}"
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)

    return None
