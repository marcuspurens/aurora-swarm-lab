"""Helpers for source_id and source_version."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def make_source_id(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def parse_source_id(source_id: str) -> tuple[str, str]:
    if ":" not in source_id:
        raise ValueError(f"Invalid source_id: {source_id}")
    kind, value = source_id.split(":", 1)
    return kind, value


def safe_source_id(source_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", source_id)
    return safe[:200]
