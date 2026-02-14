"""Translator utility — translates text to Chinese using Google Translate."""

from __future__ import annotations


def translate_to_chinese(text: str) -> str:
    """Translate text to Chinese (Simplified) using deep-translator.

    Returns the original text unchanged if translation fails or if the
    input is empty.

    Args:
        text: The text to translate.

    Returns:
        The translated text, or the original text on failure.
    """
    if not text or not text.strip():
        return text

    try:
        from deep_translator import GoogleTranslator

        result = GoogleTranslator(source="auto", target="zh-CN").translate(text)
        return result or text
    except Exception:
        return text
