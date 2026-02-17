"""Allowlist enforcement for local file ingest paths."""

from __future__ import annotations

from pathlib import Path
from typing import List

from app.core.config import Settings, load_settings

_LIST_SPLIT_CHARS = {",", ";", "\n"}


def ensure_ingest_path_allowed(path: Path | str, source: str = "local_file") -> Path:
    settings = load_settings()
    resolved = Path(path).expanduser().resolve()

    if not settings.ingest_path_allowlist_enforced:
        return resolved

    roots = configured_ingest_allowlist_roots(settings)
    if not roots:
        raise PermissionError(
            f"{source} blocked: no ingest allowlist configured. "
            "Set AURORA_INGEST_PATH_ALLOWLIST or disable AURORA_INGEST_PATH_ALLOWLIST_ENFORCED."
        )

    if _is_under_roots(resolved, roots):
        return resolved

    allowlist_preview = ", ".join(str(root) for root in roots[:4])
    if len(roots) > 4:
        allowlist_preview += ", ..."
    raise PermissionError(
        f"{source} blocked for path '{resolved}'. Allowed roots: [{allowlist_preview}]"
    )


def configured_ingest_allowlist_roots(settings: Settings | None = None) -> List[Path]:
    use_settings = settings or load_settings()
    roots: List[Path] = []

    raw = str(use_settings.ingest_path_allowlist or "")
    if raw.strip():
        cleaned = raw
        for split_char in _LIST_SPLIT_CHARS:
            cleaned = cleaned.replace(split_char, "|")
        for item in cleaned.split("|"):
            candidate = Path(item.strip()).expanduser()
            if not item.strip():
                continue
            try:
                roots.append(candidate.resolve())
            except Exception:
                continue

    if use_settings.obsidian_vault_path:
        try:
            roots.append(Path(use_settings.obsidian_vault_path).expanduser().resolve())
        except Exception:
            pass

    deduped: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return deduped


def _is_under_roots(path: Path, roots: List[Path]) -> bool:
    for root in roots:
        if path == root:
            return True
        if root in path.parents:
            return True
    return False

