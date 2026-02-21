"""Chunk text into segments for downstream processing."""

from __future__ import annotations

import json
from typing import Dict, List

from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


CHUNKS_REL_PATH = "chunks/chunks.jsonl"


def _split_words(text: str, max_words: int, overlap_words: int) -> List[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    start = 0
    while start < len(words):
        end = min(len(words), start + max_words)
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end == len(words):
            break
        start = max(0, end - overlap_words)
    return chunks


def chunk(text: str, doc_id: str, max_words: int = 200, overlap_words: int = 20) -> List[Dict[str, object]]:
    parts = _split_words(text, max_words, overlap_words)
    chunks = []
    for idx, part in enumerate(parts, start=1):
        chunks.append(
            {
                "doc_id": doc_id,
                "segment_id": f"chunk_{idx}",
                "start_ms": None,
                "end_ms": None,
                "speaker": None,
                "text": part,
                "source_refs": {"chunk_index": idx},
            }
        )
    return chunks


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for chunk_text")

    existing = artifact_path(source_id, source_version, CHUNKS_REL_PATH)
    if existing.exists():
        return

    canonical_rel = manifest.get("artifacts", {}).get("canonical_text")
    if not canonical_rel:
        raise RuntimeError("canonical_text artifact not found")

    text = read_artifact(source_id, source_version, str(canonical_rel))
    if text is None:
        raise RuntimeError("canonical_text artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="chunk_text",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    chunks = chunk(text, doc_id=source_id)
    metadata = manifest.get("metadata")
    intake_meta = metadata.get("intake") if isinstance(metadata, dict) else None
    if isinstance(intake_meta, dict):
        tags = intake_meta.get("tags")
        context = str(intake_meta.get("context") or "").strip()
        source_metadata = intake_meta.get("source_metadata")
        context_ref = context[:280] if context else ""
        speaker = ""
        organization = ""
        event_date = ""
        if isinstance(source_metadata, dict):
            speaker = str(source_metadata.get("speaker") or "").strip()
            organization = str(source_metadata.get("organization") or "").strip()
            event_date = str(source_metadata.get("event_date") or "").strip()
        for row in chunks:
            refs = row.get("source_refs")
            if not isinstance(refs, dict):
                refs = {}
            if isinstance(tags, list) and tags:
                refs["intake_tags"] = [str(tag) for tag in tags if str(tag).strip()]
            if context_ref:
                refs["intake_context"] = context_ref
            if speaker:
                refs["intake_speaker"] = speaker
            if organization:
                refs["intake_organization"] = organization
            if event_date:
                refs["intake_event_date"] = event_date
            row["source_refs"] = refs
    lines = "\n".join(json.dumps(c, ensure_ascii=True) for c in chunks)
    write_artifact(source_id, source_version, CHUNKS_REL_PATH, lines)

    manifest.setdefault("artifacts", {})["chunks"] = CHUNKS_REL_PATH
    manifest.setdefault("steps", {})["chunk_text"] = {"status": "done", "chunk_count": len(chunks)}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "oss20b")),
        component="chunk_text",
        input_json={"run_id": run_id},
        output_json={"chunk_count": len(chunks)},
    )

    enqueue_job("embed_chunks", "oss20b", source_id, source_version)
    enqueue_job("enrich_doc", "oss20b", source_id, source_version)
    enqueue_job("enrich_chunks", "oss20b", source_id, source_version)
