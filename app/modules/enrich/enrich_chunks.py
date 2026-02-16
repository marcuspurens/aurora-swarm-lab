"""Enrich chunks with topics/entities via Ollama."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import ChunkEnrichOutput
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


CHUNKS_REL_PATH = "chunks/chunks.jsonl"
ENRICH_REL_PATH = "enrich/chunks.jsonl"


def _load_chunks(text: str) -> List[Dict[str, object]]:
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.append(json.loads(line))
    return chunks


def _prompt(text: str) -> str:
    return (
        "Return ONLY valid JSON with keys: topics, entities. "
        "topics and entities are arrays of short strings.\n\n"
        f"Text:\n{text}\n"
    )


def enrich_chunk(text: str) -> ChunkEnrichOutput:
    settings = load_settings()
    return generate_json(_prompt(text), settings.ollama_model_fast, ChunkEnrichOutput)


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for enrich_chunks")

    existing = artifact_path(source_id, source_version, ENRICH_REL_PATH)
    if existing.exists():
        return

    chunks_rel = manifest.get("artifacts", {}).get("chunks")
    if not chunks_rel:
        raise RuntimeError("chunks artifact not found")

    chunk_text = read_artifact(source_id, source_version, str(chunks_rel))
    if chunk_text is None:
        raise RuntimeError("chunks artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="enrich_chunks",
        input_json={"source_id": source_id, "source_version": source_version},
        model=load_settings().ollama_model_fast,
    )

    try:
        chunks = _load_chunks(chunk_text)
        enriched: List[Dict[str, object]] = []
        for item in chunks:
            text = str(item.get("text", ""))
            output = enrich_chunk(text)
            payload = output.model_dump()
            item.update(payload)
            enriched.append(item)

        lines = "\n".join(json.dumps(c, ensure_ascii=True) for c in enriched)
        write_artifact(source_id, source_version, ENRICH_REL_PATH, lines)

        manifest.setdefault("artifacts", {})["enriched_chunks"] = ENRICH_REL_PATH
        manifest.setdefault("steps", {})["enrich_chunks"] = {"status": "done", "chunk_count": len(enriched)}
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane=str(job.get("lane", "oss20b")),
            component="enrich_chunks",
            input_json={"run_id": run_id},
            output_json={"chunk_count": len(enriched)},
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "oss20b")),
            component="enrich_chunks",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise

    enqueue_job("publish_snowflake", "io", source_id, source_version)
    enqueue_job("graph_ontology_seed", "io", source_id, source_version)
    enqueue_job("graph_extract_entities", "nemotron", source_id, source_version)
