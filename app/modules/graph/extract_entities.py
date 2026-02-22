"""Entity + claim extraction for GraphRAG (MVP)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.ids import sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import GraphEntitiesOutput
from app.core.prompts import render_prompt
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run
from app.queue.jobs import enqueue_job


ENTITIES_REL_PATH = "graph/entities.jsonl"
CLAIMS_REL_PATH = "graph/claims.jsonl"


def _load_chunks(text: str) -> List[Dict[str, object]]:
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        chunks.append(json.loads(line))
    return chunks


def _prompt(text: str) -> str:
    return render_prompt("graph_extract_entities", input_json=text)


def _ensure_ids(entities: List[Dict[str, object]], claims: List[Dict[str, object]]) -> None:
    for e in entities:
        if not e.get("entity_id"):
            e["entity_id"] = sha256_text(f"{e.get('name','')}-{e.get('type','')}")
    for c in claims:
        if not c.get("claim_id"):
            c["claim_id"] = sha256_text(c.get("claim_text", ""))


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for extract_entities")

    if artifact_path(source_id, source_version, ENTITIES_REL_PATH).exists():
        return

    chunks_rel = manifest.get("artifacts", {}).get("enriched_chunks") or manifest.get("artifacts", {}).get("chunks")
    if not chunks_rel:
        raise RuntimeError("chunks artifact not found")

    chunk_text = read_artifact(source_id, source_version, str(chunks_rel))
    if chunk_text is None:
        raise RuntimeError("chunks artifact missing on disk")

    chunks = _load_chunks(chunk_text)
    sample = chunks[:20]
    prompt_payload = json.dumps(sample, ensure_ascii=True)

    settings = load_settings()
    run_id = log_run(
        lane="nemotron",
        component="graph_extract_entities",
        input_json={"source_id": source_id, "source_version": source_version, "chunks": len(sample)},
        model=settings.ollama_model_strong,
    )

    try:
        output = generate_json(_prompt(prompt_payload), settings.ollama_model_strong, GraphEntitiesOutput)
        entities = [e.model_dump() for e in output.entities]
        claims = [c.model_dump() for c in output.claims]
        _ensure_ids(entities, claims)

        ent_lines = "\n".join(json.dumps(e, ensure_ascii=True) for e in entities)
        clm_lines = "\n".join(json.dumps(c, ensure_ascii=True) for c in claims)
        write_artifact(source_id, source_version, ENTITIES_REL_PATH, ent_lines)
        write_artifact(source_id, source_version, CLAIMS_REL_PATH, clm_lines)

        manifest.setdefault("artifacts", {})["graph_entities"] = ENTITIES_REL_PATH
        manifest.setdefault("artifacts", {})["graph_claims"] = CLAIMS_REL_PATH
        manifest.setdefault("steps", {})["graph_extract_entities"] = {"status": "done", "entity_count": len(entities)}
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane="nemotron",
            component="graph_extract_entities",
            input_json={"run_id": run_id},
            output_json={"entities": len(entities), "claims": len(claims)},
        )
        enqueue_job("graph_extract_relations", "nemotron", source_id, source_version)
    except Exception as exc:
        log_run(
            lane="nemotron",
            component="graph_extract_entities",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
