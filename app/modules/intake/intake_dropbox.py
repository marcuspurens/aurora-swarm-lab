"""Watch configured folders and auto-enqueue new/updated files."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.core.ids import make_source_id, sha256_file
from app.modules.security.ingest_allowlist import ensure_ingest_path_allowed
from app.queue.db import get_conn
from app.queue.jobs import enqueue_job


_LIST_SPLIT_CHARS = {",", ";", "\n"}
_SKIP_SUFFIXES = {".tmp", ".part", ".crdownload", ".download"}


def _parse_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def configured_dropbox_roots(raw: Optional[str] = None) -> List[Path]:
    text = str(raw or os.getenv("AURORA_DROPBOX_PATHS", "")).strip()
    if not text:
        return []
    cleaned = text
    for split_char in _LIST_SPLIT_CHARS:
        cleaned = cleaned.replace(split_char, "|")
    roots: List[Path] = []
    seen = set()
    for item in cleaned.split("|"):
        token = item.strip()
        if not token:
            continue
        path = Path(token).expanduser().resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        roots.append(path)
    return roots


def _should_skip(path: Path) -> bool:
    if path.is_dir():
        return True
    if not path.exists():
        return True
    if path.name.startswith("."):
        return True
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return True
    if any(part.startswith(".") for part in path.parts):
        return True
    return False


def _manifest_exists(source_id: str, source_version: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT 1 FROM manifests WHERE source_id=? AND source_version=? LIMIT 1",
                (source_id, source_version),
            )
        else:
            cur.execute(
                "SELECT 1 FROM manifests WHERE source_id=%s AND source_version=%s LIMIT 1",
                (source_id, source_version),
            )
        return cur.fetchone() is not None


def _ingest_job_pending(source_id: str, source_version: str) -> bool:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT 1 FROM jobs WHERE job_type='ingest_doc' AND source_id=? AND source_version=? AND status IN ('queued','running') LIMIT 1",
                (source_id, source_version),
            )
        else:
            cur.execute(
                "SELECT 1 FROM jobs WHERE job_type='ingest_doc' AND source_id=%s AND source_version=%s AND status IN ('queued','running') LIMIT 1",
                (source_id, source_version),
            )
        return cur.fetchone() is not None


def enqueue_file_if_needed(path: Path) -> Dict[str, object]:
    if _should_skip(path):
        return {"status": "skipped", "reason": "not_ingestable"}

    safe_path = ensure_ingest_path_allowed(path, source="dropbox_watch")
    source_id = make_source_id("file", str(safe_path))
    source_version = sha256_file(safe_path)

    if _manifest_exists(source_id, source_version):
        return {"status": "skipped", "reason": "already_manifested", "source_id": source_id}
    if _ingest_job_pending(source_id, source_version):
        return {"status": "skipped", "reason": "already_queued", "source_id": source_id}

    job_id = enqueue_job("ingest_doc", "io", source_id, source_version)
    return {"status": "queued", "job_id": job_id, "source_id": source_id, "source_version": source_version}


def scan_dropboxes_once(roots: Optional[List[Path]] = None, recursive: Optional[bool] = None) -> Dict[str, int]:
    use_roots = roots or configured_dropbox_roots()
    if not use_roots:
        raise RuntimeError("AURORA_DROPBOX_PATHS not set")
    use_recursive = _parse_bool(os.getenv("AURORA_DROPBOX_RECURSIVE"), True) if recursive is None else recursive

    queued = 0
    skipped = 0
    errors = 0
    for root in use_roots:
        if not root.exists() or not root.is_dir():
            continue
        iterator = root.rglob("*") if use_recursive else root.glob("*")
        for candidate in iterator:
            if candidate.is_dir():
                continue
            try:
                result = enqueue_file_if_needed(candidate)
                if result.get("status") == "queued":
                    queued += 1
                else:
                    skipped += 1
            except Exception:
                errors += 1
    return {"roots": len(use_roots), "queued": queued, "skipped": skipped, "errors": errors}


class _DropboxHandler(FileSystemEventHandler):
    def __init__(self, debounce_seconds: float = 1.2):
        super().__init__()
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self._last_seen: Dict[str, float] = {}

    def _handle_path(self, raw: str) -> None:
        path = Path(raw).expanduser().resolve()
        now = time.monotonic()
        key = str(path)
        last = self._last_seen.get(key, 0.0)
        if (now - last) < self.debounce_seconds:
            return
        self._last_seen[key] = now
        try:
            enqueue_file_if_needed(path)
        except Exception:
            return

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._handle_path(event.src_path)

    def on_modified(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._handle_path(event.src_path)

    def on_moved(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        self._handle_path(event.dest_path)


def watch_dropboxes() -> None:
    roots = configured_dropbox_roots()
    if not roots:
        raise RuntimeError("AURORA_DROPBOX_PATHS not set")
    recursive = _parse_bool(os.getenv("AURORA_DROPBOX_RECURSIVE"), True)
    scan_on_start = _parse_bool(os.getenv("AURORA_DROPBOX_SCAN_ON_START"), True)
    debounce_seconds = float(str(os.getenv("AURORA_DROPBOX_DEBOUNCE_SECONDS", "1.2")).strip() or "1.2")

    observer = Observer()
    handler = _DropboxHandler(debounce_seconds=debounce_seconds)
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        observer.schedule(handler, str(root), recursive=recursive)

    if scan_on_start:
        try:
            scan_dropboxes_once(roots=roots, recursive=recursive)
        except Exception:
            pass

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
