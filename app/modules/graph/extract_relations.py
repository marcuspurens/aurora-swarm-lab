"""Relation extraction for GraphRAG (MVP)."""

from __future__ import annotations

import json
import os
from typing import Dict, List

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.ids import sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import GraphRelationsOutput
from app.core.prompts import render_prompt
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.modules.graph.ontology_rules import (
    canonical_default_rules,
    normalize_entity_type,
    render_allowed_predicate_lines,
    validate_relations,
)
from app.queue.logs import log_run
from app.queue.jobs import enqueue_job


RELATIONS_REL_PATH = "graph/relations.jsonl"
RELATIONS_INVALID_REL_PATH = "graph/relations_invalid.jsonl"
_DEFAULT_MAX_CHUNKS = 20


def _load_jsonl(text: str) -> List[Dict[str, object]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _max_chunks() -> int:
    raw = str(os.getenv("AURORA_GRAPH_RELATIONS_MAX_CHUNKS", str(_DEFAULT_MAX_CHUNKS))).strip()
    try:
        value = int(raw)
    except Exception:
        return _DEFAULT_MAX_CHUNKS
    return max(1, value)


def _prompt(chunks: List[Dict[str, object]], entities: List[Dict[str, object]], allowed_predicates: str) -> str:
    return render_prompt(
        "graph_extract_relations",
        allowed_predicates=allowed_predicates,
        entities_json=json.dumps(entities, ensure_ascii=True),
        chunks_json=json.dumps(chunks, ensure_ascii=True),
    )


def _ensure_ids(relations: List[Dict[str, object]]) -> None:
    for r in relations:
        if not r.get("rel_id"):
            base = f"{r.get('subj_entity_id','')}-{r.get('predicate','')}-{r.get('obj_entity_id','')}"
            r["rel_id"] = sha256_text(base)


def _load_ontology_rows(source_id: str, source_version: str, manifest: Dict[str, object]) -> List[Dict[str, object]]:
    rel = manifest.get("artifacts", {}).get("ontology")
    if not rel:
        return canonical_default_rules()
    text = read_artifact(source_id, source_version, str(rel))
    if not text:
        return canonical_default_rules()
    try:
        parsed = json.loads(text)
    except Exception:
        return canonical_default_rules()
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return canonical_default_rules()


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

    chunks = _load_jsonl(chunk_text)[: _max_chunks()]
    entities = _load_jsonl(ent_text)
    ontology_rows = _load_ontology_rows(source_id, source_version, manifest)
    allowed_predicates = render_allowed_predicate_lines(ontology_rows)

    settings = load_settings()
    run_id = log_run(
        lane="nemotron",
        component="graph_extract_relations",
        input_json={
            "source_id": source_id,
            "source_version": source_version,
            "entities": len(entities),
            "ontology_rules": len(ontology_rows),
        },
        model=settings.ollama_model_strong,
    )

    try:
        output = generate_json(
            _prompt(chunks, entities, allowed_predicates),
            settings.ollama_model_strong,
            GraphRelationsOutput,
        )
        relations = [r.model_dump() for r in output.relations]
        _ensure_ids(relations)
        entity_types = {
            str(e.get("entity_id") or ""): normalize_entity_type(e.get("type") or "Entity")
            for e in entities
            if str(e.get("entity_id") or "").strip()
        }
        # Relations frequently use doc_id/source_id as subject for Document predicates.
        # Ensure those IDs are typed as Document during ontology validation.
        entity_types[str(source_id)] = "Document"
        for c in chunks:
            doc_id = str(c.get("doc_id") or "").strip()
            if doc_id:
                entity_types[doc_id] = "Document"
        validation = validate_relations(relations, entity_types=entity_types, rules=ontology_rows)
        valid_relations = list(validation["valid_relations"])
        invalid_relations = list(validation["invalid_relations"])

        rel_lines = "\n".join(json.dumps(r, ensure_ascii=True) for r in valid_relations)
        write_artifact(source_id, source_version, RELATIONS_REL_PATH, rel_lines)
        if invalid_relations:
            invalid_lines = "\n".join(json.dumps(r, ensure_ascii=True) for r in invalid_relations)
            write_artifact(source_id, source_version, RELATIONS_INVALID_REL_PATH, invalid_lines)

        manifest.setdefault("artifacts", {})["graph_relations"] = RELATIONS_REL_PATH
        if invalid_relations:
            manifest.setdefault("artifacts", {})["graph_relations_invalid"] = RELATIONS_INVALID_REL_PATH
        manifest.setdefault("steps", {})["graph_extract_relations"] = {
            "status": "done",
            "relation_count": len(valid_relations),
            "invalid_relation_count": len(invalid_relations),
        }
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane="nemotron",
            component="graph_extract_relations",
            input_json={"run_id": run_id},
            output_json={
                "relations": len(valid_relations),
                "invalid_relations": len(invalid_relations),
                "ontology_rules": int(validation.get("summary", {}).get("rules") or 0),
            },
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
