"""Shared helpers for auto-ingesting pasted items (URLs, YouTube, files)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import unquote, urlparse

from app.clients.youtube_client import get_video_info
from app.core.ids import make_source_id, sha256_file
from app.core.manifest import get_manifest, upsert_manifest
from app.core.timeutil import utc_now
from app.modules.intake.intake_url import compute_source_version as compute_url_version
from app.modules.intake.intake_youtube import compute_source_version as compute_youtube_version
from app.modules.security.ingest_allowlist import ensure_ingest_path_allowed
from app.queue.jobs import enqueue_job


_URL_RE = re.compile(r"https?://\S+")
_TRAILING_PUNCT = ".,);:!?]"


def _max_files_per_dir() -> int:
    raw = str(os.getenv("AURORA_INGEST_AUTO_MAX_FILES_PER_DIR", "500")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 500
    return max(1, min(10000, value))


def _clean_url(url: str) -> str:
    return url.rstrip(_TRAILING_PUNCT)


def _normalize_tags(tags: Optional[Iterable[object]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in tags or []:
        for token in str(raw or "").replace("\n", ",").split(","):
            tag = token.strip()
            if not tag:
                continue
            if len(tag) > 64:
                tag = tag[:64]
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(tag)
    return out


def _normalize_context(value: object) -> str:
    context = str(value or "").strip()
    if len(context) > 4000:
        return context[:4000]
    return context


def _normalize_short_text(value: object, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _normalize_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    return ""


def _normalize_source_metadata(
    source_metadata: object,
    speaker: object = "",
    organization: object = "",
    event_date: object = "",
) -> Dict[str, object]:
    out: Dict[str, object] = {}
    if isinstance(source_metadata, dict):
        for k, v in source_metadata.items():
            key = str(k or "").strip()
            if not key:
                continue
            if isinstance(v, list):
                out[key] = [str(item) for item in v if str(item or "").strip()]
                continue
            if isinstance(v, (str, int, float, bool)) or v is None or isinstance(v, dict):
                out[key] = v

    speaker_value = _normalize_short_text(speaker)
    organization_value = _normalize_short_text(organization)
    event_date_value = _normalize_date(event_date)
    if speaker_value:
        out["speaker"] = speaker_value
    if organization_value:
        out["organization"] = organization_value
    if event_date_value:
        out["event_date"] = event_date_value
    return out


def _seed_manifest_annotations(
    source_id: str,
    source_version: str,
    source_type: str,
    source_uri: str,
    tags: List[str],
    context: str,
    source_metadata: Dict[str, object],
) -> None:
    if not tags and not context and not source_metadata:
        return

    manifest = get_manifest(source_id, source_version) or {
        "source_id": source_id,
        "source_version": source_version,
        "source_type": source_type,
        "source_uri": source_uri,
        "artifacts": {},
        "steps": {},
    }
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    intake_meta = metadata.get("intake")
    if not isinstance(intake_meta, dict):
        intake_meta = {}

    merged_tags = _normalize_tags(list(intake_meta.get("tags") or []) + tags)
    if merged_tags:
        intake_meta["tags"] = merged_tags
    if context:
        intake_meta["context"] = context
        contexts = list(intake_meta.get("contexts") or [])
        if context not in contexts:
            contexts.append(context)
        intake_meta["contexts"] = contexts[-8:]
    if source_metadata:
        existing_source_metadata = intake_meta.get("source_metadata")
        merged_source_metadata: Dict[str, object] = {}
        if isinstance(existing_source_metadata, dict):
            merged_source_metadata.update(existing_source_metadata)
        merged_source_metadata.update(source_metadata)
        intake_meta["source_metadata"] = merged_source_metadata
    intake_meta["updated_at"] = utc_now().isoformat()

    ebucore_plus = metadata.get("ebucore_plus")
    if not isinstance(ebucore_plus, dict):
        ebucore_plus = {}
    ebucore_plus["schema"] = "ebucore_plus.intake.v1"
    speaker = str(source_metadata.get("speaker") or "").strip()
    if speaker:
        speaker_node = ebucore_plus.get("speaker")
        if not isinstance(speaker_node, dict):
            speaker_node = {}
        speaker_node["name"] = speaker
        ebucore_plus["speaker"] = speaker_node
    organization = str(source_metadata.get("organization") or "").strip()
    if organization:
        org_node = ebucore_plus.get("organization")
        if not isinstance(org_node, dict):
            org_node = {}
        org_node["name"] = organization
        org_uri = str(source_metadata.get("organization_uri") or source_metadata.get("organization_url") or "").strip()
        if org_uri:
            org_node["uri"] = org_uri
        ebucore_plus["organization"] = org_node
    event_date = _normalize_date(source_metadata.get("event_date"))
    if event_date:
        ebucore_plus["event_date"] = event_date
    if str(source_metadata.get("title") or "").strip():
        ebucore_plus["title"] = str(source_metadata.get("title") or "").strip()
    metadata["ebucore_plus"] = ebucore_plus

    metadata["intake"] = intake_meta
    manifest["metadata"] = metadata
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)


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


def _iter_files_under(root: Path, max_files: int) -> tuple[List[Path], bool]:
    files: List[Path] = []
    truncated = False
    for candidate in sorted(root.rglob("*")):
        if candidate.is_dir():
            continue
        if candidate.name.startswith("."):
            continue
        if any(part.startswith(".") for part in candidate.parts):
            continue
        files.append(candidate.resolve())
        if len(files) >= max_files:
            truncated = True
            break
    return files, truncated


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


def enqueue_items(
    items: Iterable[str],
    base_dir: Optional[Path] = None,
    tags: Optional[Iterable[object]] = None,
    context: object = "",
    speaker: object = "",
    organization: object = "",
    event_date: object = "",
    source_metadata: object = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    seen_files = set()
    max_files = _max_files_per_dir()
    normalized_tags = _normalize_tags(tags)
    normalized_context = _normalize_context(context)
    normalized_source_metadata = _normalize_source_metadata(
        source_metadata=source_metadata,
        speaker=speaker,
        organization=organization,
        event_date=event_date,
    )
    for item in items:
        try:
            if item.startswith(("http://", "https://")):
                if _is_youtube_url(item):
                    info = get_video_info(item)
                    video_id = str(info.get("id") or "unknown")
                    source_id = make_source_id("youtube", video_id)
                    source_version = compute_youtube_version(item)
                    _seed_manifest_annotations(
                        source_id=source_id,
                        source_version=source_version,
                        source_type="youtube",
                        source_uri=item,
                        tags=normalized_tags,
                        context=normalized_context,
                        source_metadata=normalized_source_metadata,
                    )
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
                    _seed_manifest_annotations(
                        source_id=source_id,
                        source_version=source_version,
                        source_type="url",
                        source_uri=item,
                        tags=normalized_tags,
                        context=normalized_context,
                        source_metadata=normalized_source_metadata,
                    )
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
                if path.is_dir():
                    folder = ensure_ingest_path_allowed(path, source="ingest_auto")
                    file_paths, truncated = _iter_files_under(folder, max_files=max_files)
                    if not file_paths:
                        results.append({"input": item, "kind": "folder", "error": "No files found in folder"})
                        continue
                    for file_path in file_paths:
                        if str(file_path) in seen_files:
                            continue
                        seen_files.add(str(file_path))
                        safe_path = ensure_ingest_path_allowed(file_path, source="ingest_auto")
                        source_id = make_source_id("file", str(safe_path))
                        source_version = sha256_file(safe_path)
                        _seed_manifest_annotations(
                            source_id=source_id,
                            source_version=source_version,
                            source_type="file",
                            source_uri=str(safe_path),
                            tags=normalized_tags,
                            context=normalized_context,
                            source_metadata=normalized_source_metadata,
                        )
                        job_id = enqueue_job("ingest_doc", "io", source_id, source_version)
                        results.append(
                            {
                                "input": str(file_path),
                                "kind": "doc",
                                "result": {"job_id": job_id, "source_id": source_id, "source_version": source_version},
                            }
                        )
                    if truncated:
                        results.append(
                            {
                                "input": item,
                                "kind": "folder",
                                "warning": f"Folder truncated at {max_files} files (set AURORA_INGEST_AUTO_MAX_FILES_PER_DIR to change).",
                            }
                        )
                    continue
                path = ensure_ingest_path_allowed(path, source="ingest_auto")
                if str(path) in seen_files:
                    continue
                seen_files.add(str(path))
                source_id = make_source_id("file", str(path))
                source_version = sha256_file(path)
                _seed_manifest_annotations(
                    source_id=source_id,
                    source_version=source_version,
                    source_type="file",
                    source_uri=str(path),
                    tags=normalized_tags,
                    context=normalized_context,
                    source_metadata=normalized_source_metadata,
                )
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
