"""Embed chunks and store vectors for retrieval."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.ollama_client import embed
from app.core.config import load_settings
from app.core.ids import sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact
from app.core.timeutil import utc_now
from app.modules.embeddings.embedding_store import get_embedding_hashes, upsert_embedding
from app.queue.logs import log_run


CHUNKS_REL_PATH = "chunks/chunks.jsonl"


def _load_chunks(text: str) -> List[Dict[str, object]]:
    chunks: List[Dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.append(json.loads(line))
    return chunks


def handle_job(job: Dict[str, object]) -> None:
    settings = load_settings()
    if not settings.embeddings_enabled:
        return

    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for embed_chunks")

    existing = artifact_path(source_id, source_version, CHUNKS_REL_PATH)
    if not existing.exists():
        raise RuntimeError("chunks artifact not found")

    chunks_text = read_artifact(source_id, source_version, CHUNKS_REL_PATH)
    if chunks_text is None:
        raise RuntimeError("chunks artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="embed_chunks",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    chunks = _load_chunks(chunks_text)
    existing_hashes = get_embedding_hashes(source_id)
    embedded = 0
    for chunk in chunks:
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        segment_id = str(chunk.get("segment_id"))
        text_hash = sha256_text(text)
        if existing_hashes.get(segment_id) == text_hash:
            continue
        vector = embed(text)
        upsert_embedding(
            {
                "doc_id": source_id,
                "segment_id": segment_id,
                "source_id": source_id,
                "source_version": source_version,
                "text": text,
                "text_hash": text_hash,
                "embedding": vector,
                "start_ms": chunk.get("start_ms"),
                "end_ms": chunk.get("end_ms"),
                "speaker": chunk.get("speaker"),
                "source_refs": chunk.get("source_refs") or {},
            }
        )
        embedded += 1

    manifest.setdefault("steps", {})["embed_chunks"] = {"status": "done", "embedded": embedded}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "oss20b")),
        component="embed_chunks",
        input_json={"run_id": run_id},
        output_json={"embedded": embedded},
    )
