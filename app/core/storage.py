"""Artifact storage helper."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import load_settings
from app.core.ids import safe_source_id


def artifact_root() -> Path:
    settings = load_settings()
    root = settings.artifact_root
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_dir(source_id: str, source_version: str) -> Path:
    base = artifact_root() / safe_source_id(source_id) / source_version
    base.mkdir(parents=True, exist_ok=True)
    return base


def artifact_path(source_id: str, source_version: str, rel_path: str) -> Path:
    return artifact_dir(source_id, source_version) / rel_path


def write_artifact(source_id: str, source_version: str, rel_path: str, data: str) -> Path:
    path = artifact_path(source_id, source_version, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    return path


def write_artifact_bytes(source_id: str, source_version: str, rel_path: str, data: bytes) -> Path:
    path = artifact_path(source_id, source_version, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def read_artifact(source_id: str, source_version: str, rel_path: str) -> Optional[str]:
    path = artifact_path(source_id, source_version, rel_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def read_artifact_bytes(source_id: str, source_version: str, rel_path: str) -> Optional[bytes]:
    path = artifact_path(source_id, source_version, rel_path)
    if not path.exists():
        return None
    return path.read_bytes()
