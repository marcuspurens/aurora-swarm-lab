"""Relation extraction for GraphRAG (MVP)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.ids import sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import GraphRelationsOutput
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run
from app.queue.jobs import enqueue_job


RELATIONS_REL_PATH = "graph/relations.jsonl"


def _load_jsonl(text: str) -> List[Dict[str, object]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _prompt(chunks: List[Dict[str, object]], entities: List[Dict[str, object]]) -> str:
    return (
        "Return ONLY valid JSON with key: relations. "
        "relations is a list of {rel_id, subj_entity_id, predicate, obj_entity_id, doc_id, segment_id, confidence}. "
        "Use provided entity_id values.\n\n"
        f"Entities:\n{json.dumps(entities, ensure_ascii=True)}\n\n"
        f"Chunks:\n{json.dumps(chunks, ensure_ascii=True)}\n"
    )


def _ensure_ids(relations: List[Dict[str, object]]) -> None:
    for r in relations:
        if not r.get("rel_id"):
            base = f"{r.get('subj_entity_id','')}-{r.get('predicate','')}-{r.get('obj_entity_id','')}"
            r["rel_id"] = sha256_text(base)


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for extract_relations")

    if artifact_path(source_id, source_version, RELATIONS_REL_PATH).exists():
        return

    chunks_rel = manifest.get("artifacts", {}).get("enriched_chunks") or manifest.get("artifacts", {}).get("chunks")
    entities_rel = manifest.get("artifacts", {}).get("graph_entities")
    if not chunks_rel or not entities_rel:
        raise RuntimeError("chunks or entities artifacts missing")

    chunk_text = read_artifact(source_id, source_version, str(chunks_rel))
    ent_text = read_artifact(source_id, source_version, str(entities_rel))
    if chunk_text is None or ent_text is None:
        raise RuntimeError("chunks/entities artifacts missing on disk")

    chunks = _load_jsonl(chunk_text)[:20]
    entities = _load_jsonl(ent_text)

    settings = load_settings()
    run_id = log_run(
        lane="nemotron",
        component="graph_extract_relations",
        input_json={"source_id": source_id, "source_version": source_version, "entities": len(entities)},
        model=settings.ollama_model_strong,
    )

    try:
        output = generate_json(_prompt(chunks, entities), settings.ollama_model_strong, GraphRelationsOutput)
        relations = [r.model_dump() for r in output.relations]
        _ensure_ids(relations)

        rel_lines = "\n".join(json.dumps(r, ensure_ascii=True) for r in relations)
        write_artifact(source_id, source_version, RELATIONS_REL_PATH, rel_lines)

        manifest.setdefault("artifacts", {})["graph_relations"] = RELATIONS_REL_PATH
        manifest.setdefault("steps", {})["graph_extract_relations"] = {"status": "done", "relation_count": len(relations)}
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane="nemotron",
            component="graph_extract_relations",
            input_json={"run_id": run_id},
            output_json={"relations": len(relations)},
        )
        enqueue_job("graph_publish", "io", source_id, source_version)
    except Exception as exc:
        log_run(
            lane="nemotron",
            component="graph_extract_relations",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
