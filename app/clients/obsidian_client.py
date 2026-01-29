"""Obsidian client stub for future vault integration."""

from __future__ import annotations

from pathlib import Path

from app.core.config import load_settings


def vault_path() -> Path:
    settings = load_settings()
    if not settings.obsidian_vault_path:
        raise RuntimeError("OBSIDIAN_VAULT_PATH not set")
    return settings.obsidian_vault_path
