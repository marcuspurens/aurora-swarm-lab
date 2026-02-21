"""Prompt template loader."""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Dict


_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_CACHE: Dict[str, str] = {}


def load_prompt(name: str) -> str:
    key = str(name or "").strip()
    if not key:
        raise ValueError("prompt name is required")
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    path = _PROMPTS_DIR / f"{key}.txt"
    if not path.exists():
        raise RuntimeError(f"Prompt template not found: {path}")
    text = path.read_text(encoding="utf-8")
    _CACHE[key] = text
    return text


def render_prompt(name: str, **values: object) -> str:
    template = Template(load_prompt(name))
    mapping = {str(k): str(v) for k, v in values.items()}
    return template.substitute(mapping)
