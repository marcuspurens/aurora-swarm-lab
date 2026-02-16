"""Chunk transcript segments into combined chunks."""

from __future__ import annotations

import json
from typing import Dict, List

from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


CHUNKS_REL_PATH = "chunks/chunks.jsonl"


def _load_segments(text: str) -> List[Dict[str, object]]:
    segments = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        segments.append(json.loads(line))
    return segments


def chunk(segments: List[Dict[str, object]], doc_id: str, max_chars: int = 800) -> List[Dict[str, object]]:
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
    chunks = chunk(segments, doc_id=source_id)
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
