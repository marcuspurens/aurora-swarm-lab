"""Text normalization helpers."""

from __future__ import annotations

import re
import unicodedata


def normalize_whitespace(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_user_text(value: object, max_len: int = 4000) -> str:
    text = normalize_whitespace(str(value or ""))
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip()


def normalize_identifier(value: object, max_len: int = 120) -> str:
    text = normalize_whitespace(str(value or ""))
    if len(text) <= max_len:
        return text
    return text[:max_len].rstrip()
