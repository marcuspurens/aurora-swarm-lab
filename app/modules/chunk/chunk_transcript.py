"""Chunk transcript segments into combined chunks."""

from __future__ import annotations

import json
from typing import Dict, List

from app.core.config import load_settings
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.modules.chunk.summarize_chunk import summarize_chunk
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


CHUNKS_REL_PATH = "chunks/chunks.jsonl"


def _load_segments(text: str) -> List[Dict[str, object]]:
    segments: List[Dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        segments.append(json.loads(line))
    return segments


def chunk(
    segments: List[Dict[str, object]],
    doc_id: str,
    max_chars: int = 800,
    source_context: str = "",
) -> List[Dict[str, object]]:
    """Combine transcript segments into chunks with optional AI summaries."""
    chunks: List[Dict[str, object]] = []
    current: List[Dict[str, object]] = []
    current_len = 0
    chunk_idx = 0

    def flush() -> None:
        nonlocal chunk_idx, current, current_len
        if not current:
            return
        chunk_idx += 1
        text = " ".join(str(seg.get("text", "")) for seg in current).strip()
        start_ms = current[0].get("start_ms")
        end_ms = current[-1].get("end_ms")
        speakers = {seg.get("speaker_local_id") for seg in current}
        speaker = current[0].get("speaker_local_id") if len(speakers) == 1 else "MIXED"
        chunks.append(
            {
                "doc_id": doc_id,
                "segment_id": f"tchunk_{chunk_idx}",
                "start_ms": start_ms,
                "end_ms": end_ms,
                "speaker": speaker,
                "text": text,
                "source_refs": {"segment_ids": [seg.get("segment_id") for seg in current]},
            }
        )
        current = []
        current_len = 0

    for seg in segments:
        seg_text = str(seg.get("text", ""))
        if not seg_text:
            continue
        if current_len + len(seg_text) > max_chars and current:
            flush()
        current.append(seg)
        current_len += len(seg_text)

    flush()

    settings = load_settings()
    if settings.chunk_summaries_enabled:
        for c in chunks:
            chunk_text_val = str(c.get("text", ""))
            speaker_val = str(c.get("speaker") or "")
            start_ms_val = c.get("start_ms")
            end_ms_val = c.get("end_ms")
            ctx = source_context
            if speaker_val and speaker_val != "MIXED":
                time_part = ""
                if isinstance(start_ms_val, (int, float)) and isinstance(
                    end_ms_val, (int, float)
                ):
                    time_part = (
                        f"Time: {int(start_ms_val) // 1000}s-"
                        f"{int(end_ms_val) // 1000}s"
                    )
                parts = [f"Speaker: {speaker_val}"]
                if time_part:
                    parts.append(time_part)
                if source_context:
                    parts.append(source_context)
                ctx = ", ".join(parts)
            summary = summarize_chunk(chunk_text_val, context=ctx)
            c["summary"] = summary
            c["text_to_embed"] = (
                f"Summary: {summary}\n{chunk_text_val}" if summary else chunk_text_val
            )
    else:
        for c in chunks:
            c["summary"] = ""
            c["text_to_embed"] = str(c.get("text", ""))

    return chunks


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for chunk_transcript")

    existing = artifact_path(source_id, source_version, CHUNKS_REL_PATH)
    if existing.exists():
        return

    segments_rel = manifest.get("artifacts", {}).get("segments")
    if not segments_rel:
        raise RuntimeError("segments artifact not found")

    seg_text = read_artifact(source_id, source_version, str(segments_rel))
    if seg_text is None:
        raise RuntimeError("segments artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="chunk_transcript",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    segments = _load_segments(seg_text)

    # Build source context for chunk summaries
    source_context = ""
    metadata = manifest.get("metadata")
    intake_meta = metadata.get("intake") if isinstance(metadata, dict) else None
    if isinstance(intake_meta, dict):
        source_metadata = intake_meta.get("source_metadata")
        if isinstance(source_metadata, dict):
            ctx_parts: list[str] = []
            speaker = str(source_metadata.get("speaker") or "").strip()
            if speaker:
                ctx_parts.append(f"Speaker: {speaker}")
            organization = str(source_metadata.get("organization") or "").strip()
            if organization:
                ctx_parts.append(f"Organization: {organization}")
            source_context = ", ".join(ctx_parts)

    chunks = chunk(segments, doc_id=source_id, source_context=source_context)

    # Enrich chunks with intake metadata
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
    manifest.setdefault("steps", {})["chunk_transcript"] = {"status": "done", "chunk_count": len(chunks)}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "oss20b")),
        component="chunk_transcript",
        input_json={"run_id": run_id},
        output_json={"chunk_count": len(chunks)},
    )

    enqueue_job("embed_chunks", "oss20b", source_id, source_version)
    enqueue_job("enrich_chunks", "oss20b", source_id, source_version)
