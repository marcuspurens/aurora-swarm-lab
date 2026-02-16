"""Build graph entities/relations from Voice Gallery EBUCore+ metadata."""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

from app.core.ids import sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import write_artifact
from app.core.timeutil import utc_now
from app.modules.voiceprint.gallery import load_gallery
from app.queue.logs import log_run
from app.queue.jobs import enqueue_job


ENTITIES_REL_PATH = "graph/entities.jsonl"
RELATIONS_REL_PATH = "graph/relations.jsonl"
CLAIMS_REL_PATH = "graph/claims.jsonl"
ONTOLOGY_REL_PATH = "graph/ontology.json"


def _entity_id(value: str) -> str:
    return sha256_text(value)


def _normalize_name(entry: Dict[str, object]) -> str:
    for key in ("display_name", "full_name", "title", "given_name", "family_name"):
        value = entry.get(key)
        if value:
            return str(value)
    return str(entry.get("voiceprint_id") or "voiceprint")


def _parse_jsonld_graph(ebucore: Dict[str, object]) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    entities: Dict[str, Dict[str, object]] = {}
    relations: List[Dict[str, object]] = []

    graph = ebucore.get("@graph") if isinstance(ebucore, dict) else None
    if not isinstance(graph, list):
        return [], []

    for node in graph:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("@id") or _entity_id(json.dumps(node, ensure_ascii=True)))
        node_type = str(node.get("type") or node.get("@type") or "Entity")
        name_obj = node.get("ec:name") or node.get("name")
        if isinstance(name_obj, dict):
            name = str(name_obj.get("@value") or name_obj.get("value") or node_id)
        else:
            name = str(name_obj or node_id)

        entities.setdefault(
            node_id,
            {
                "entity_id": node_id,
                "name": name,
                "type": node_type,
                "aliases": [],
                "metadata": {"ebucore": node},
            },
        )

        for key, value in node.items():
            if key in {"id", "@id", "type", "@type", "ec:name", "name"}:
                continue
            if isinstance(value, dict) and ("@id" in value or "id" in value):
                obj_id = str(value.get("@id") or value.get("id"))
                relations.append(
                    {
                        "rel_id": _entity_id(f"{node_id}-{key}-{obj_id}"),
                        "subj_entity_id": node_id,
                        "predicate": key,
                        "obj_entity_id": obj_id,
                        "doc_id": "voice_gallery",
                        "segment_id": node_id,
                        "confidence": 0.7,
                    }
                )
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and ("@id" in item or "id" in item):
                        obj_id = str(item.get("@id") or item.get("id"))
                        relations.append(
                            {
                                "rel_id": _entity_id(f"{node_id}-{key}-{obj_id}"),
                                "subj_entity_id": node_id,
                                "predicate": key,
                                "obj_entity_id": obj_id,
                                "doc_id": "voice_gallery",
                                "segment_id": node_id,
                                "confidence": 0.7,
                            }
                        )

    return list(entities.values()), relations


def handle_job(job: Dict[str, object]) -> None:
    source_id = "voice_gallery"
    source_version = str(job.get("source_version") or "latest")
    run_id = log_run(
        lane=str(job.get("lane", "io")),
        component="graph_from_voice_gallery",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    data = load_gallery()
    entities: List[Dict[str, object]] = []
    relations: List[Dict[str, object]] = []
    claims: List[Dict[str, object]] = []

    for vp_id, entry in data.items():
        name = _normalize_name(entry)
        entity_id = str(entry.get("person_id") or entry.get("voiceprint_id") or vp_id)
        entities.append(
            {
                "entity_id": entity_id,
                "name": name,
                "type": "Person",
                "aliases": entry.get("aliases") or [],
                "metadata": entry,
            }
        )
        ebucore = entry.get("ebucore")
        if isinstance(ebucore, dict):
            eb_entities, eb_relations = _parse_jsonld_graph(ebucore)
            entities.extend(eb_entities)
            relations.extend(eb_relations)
            for eb_entity in eb_entities:
                relations.append(
                    {
                        "rel_id": _entity_id(f"{entity_id}-describes-{eb_entity['entity_id']}"),
                        "subj_entity_id": entity_id,
                        "predicate": "describes",
                        "obj_entity_id": eb_entity["entity_id"],
                        "doc_id": source_id,
                        "segment_id": str(entity_id),
                        "confidence": 0.6,
                    }
                )
        for org in entry.get("organizations") or []:
            org_id = _entity_id(f"org:{org}")
            entities.append(
                {
                    "entity_id": org_id,
                    "name": str(org),
                    "type": "Organisation",
                    "aliases": [],
                    "metadata": {"source": "voice_gallery"},
                }
            )
            relations.append(
                {
                    "rel_id": _entity_id(f"{entity_id}-affiliated_with-{org_id}"),
                    "subj_entity_id": entity_id,
                    "predicate": "affiliated_with",
                    "obj_entity_id": org_id,
                    "doc_id": source_id,
                    "segment_id": str(entity_id),
                    "confidence": 0.6,
                }
            )

    ent_lines = "\n".join(json.dumps(e, ensure_ascii=True) for e in entities)
    rel_lines = "\n".join(json.dumps(r, ensure_ascii=True) for r in relations)
    clm_lines = "\n".join(json.dumps(c, ensure_ascii=True) for c in claims)
    ontology = [
        {"predicate": "describes", "domain_type": "Person", "range_type": "Entity", "description": "Person describes EBUCore node"},
        {"predicate": "affiliated_with", "domain_type": "Person", "range_type": "Organisation", "description": "Person affiliation"},
    ]

    write_artifact(source_id, source_version, ENTITIES_REL_PATH, ent_lines)
    write_artifact(source_id, source_version, RELATIONS_REL_PATH, rel_lines)
    write_artifact(source_id, source_version, CLAIMS_REL_PATH, clm_lines)
    write_artifact(source_id, source_version, ONTOLOGY_REL_PATH, json.dumps(ontology, ensure_ascii=True))

    manifest = get_manifest(source_id, source_version) or {
        "source_id": source_id,
        "source_version": source_version,
        "source_type": "voice_gallery",
        "source_uri": "voice_gallery.json",
        "artifacts": {},
        "steps": {},
    }
    manifest.setdefault("artifacts", {})["graph_entities"] = ENTITIES_REL_PATH
    manifest.setdefault("artifacts", {})["graph_relations"] = RELATIONS_REL_PATH
    manifest.setdefault("artifacts", {})["graph_claims"] = CLAIMS_REL_PATH
    manifest.setdefault("artifacts", {})["ontology"] = ONTOLOGY_REL_PATH
    manifest.setdefault("steps", {})["graph_from_voice_gallery"] = {"status": "done", "entity_count": len(entities)}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "io")),
        component="graph_from_voice_gallery",
        input_json={"run_id": run_id},
        output_json={"entities": len(entities), "relations": len(relations)},
    )

    enqueue_job("graph_publish", "io", source_id, source_version)
