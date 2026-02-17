"""Shared helpers for auto-ingesting pasted items (URLs, YouTube, files)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote, urlparse

from app.clients.youtube_client import get_video_info
from app.core.ids import make_source_id, sha256_file
from app.modules.intake.intake_url import compute_source_version as compute_url_version
from app.modules.intake.intake_youtube import compute_source_version as compute_youtube_version
from app.modules.security.ingest_allowlist import ensure_ingest_path_allowed
from app.queue.jobs import enqueue_job


_URL_RE = re.compile(r"https?://\S+")
_TRAILING_PUNCT = ".,);:!?]"


def _clean_url(url: str) -> str:
    return url.rstrip(_TRAILING_PUNCT)


def _resolve_file_input(item: str, base_dir: Optional[Path] = None) -> Optional[Path]:
    if item.startswith("file://"):
        parsed = urlparse(item)
        candidate = Path(unquote(parsed.path))
    else:
        candidate = Path(item)
    if not candidate.is_absolute() and base_dir is not None:
        candidate = base_dir / candidate
    candidate = candidate.expanduser()
    if candidate.exists():
        return candidate.resolve()
    return None


def _is_youtube_url(item: str) -> bool:
    parsed = urlparse(item)
    host = (parsed.netloc or "").lower()
    return "youtube.com" in host or "youtu.be" in host


def extract_items(
    text: Optional[str] = None,
    items: Optional[Iterable[object]] = None,
    base_dir: Optional[Path] = None,
    dedupe: bool = True,
) -> List[str]:
    found: List[str] = []
    if items:
        for item in items:
            value = str(item).strip()
            if value:
                found.append(value)
    if text:
        for match in _URL_RE.findall(text):
            cleaned = _clean_url(match)
            if cleaned:
                found.append(cleaned)
        for line in text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate.startswith(("http://", "https://")):
                continue
            path = _resolve_file_input(candidate, base_dir)
            if path:
                found.append(str(path))
    if dedupe:
        seen = set()
        unique: List[str] = []
        for item in found:
            if item in seen:
                continue
            unique.append(item)
            seen.add(item)
        return unique
    return found


def enqueue_items(items: Iterable[str], base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in items:
        try:
            if item.startswith(("http://", "https://")):
                if _is_youtube_url(item):
                    info = get_video_info(item)
                    video_id = str(info.get("id") or "unknown")
                    source_id = make_source_id("youtube", video_id)
                    source_version = compute_youtube_version(item)
                    job_id = enqueue_job("ingest_youtube", "io", source_id, source_version)
                    results.append(
                        {
                            "input": item,
                            "kind": "youtube",
                            "result": {"job_id": job_id, "source_id": source_id, "source_version": source_version},
                        }
                    )
                else:
                    source_id = make_source_id("url", item)
                    source_version = compute_url_version(item)
                    job_id = enqueue_job("ingest_url", "io", source_id, source_version)
                    results.append(
                        {
                            "input": item,
                            "kind": "url",
                            "result": {"job_id": job_id, "source_id": source_id, "source_version": source_version},
                        }
                    )
                continue
            path = _resolve_file_input(item, base_dir)
            if path:
                path = ensure_ingest_path_allowed(path, source="ingest_auto")
                source_id = make_source_id("file", str(path))
                source_version = sha256_file(path)
                job_id = enqueue_job("ingest_doc", "io", source_id, source_version)
                results.append(
                    {
                        "input": item,
                        "kind": "doc",
                        "result": {"job_id": job_id, "source_id": source_id, "source_version": source_version},
                    }
                )
                continue
            results.append({"input": item, "kind": "unknown", "error": "Unsupported input"})
        except Exception as exc:
            results.append({"input": item, "kind": "error", "error": str(exc)})
    return results
