"""Translation utility — translates text to Chinese via Google Translate."""

from __future__ import annotations

from deep_translator import GoogleTranslator


_translator = GoogleTranslator(source="en", target="zh-CN")


def translate_to_chinese(text: str) -> str:
    """Translate English text to Simplified Chinese.

    Returns the original text if it appears to already be Chinese
    or if the translation fails.
    """
    if not text or not text.strip():
        return text

    # Skip if already predominantly Chinese characters
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if chinese_chars / max(len(text), 1) > 0.3:
        return text

    try:
        result = _translator.translate(text)
        return result if result else text
    except Exception:
        return text


def translate_batch(texts: list[str]) -> list[str]:
    """Translate a list of strings, preserving order."""
    return [translate_to_chinese(t) for t in texts]
