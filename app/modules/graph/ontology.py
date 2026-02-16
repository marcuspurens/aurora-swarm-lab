"""Ontology management (MVP seed)."""

from __future__ import annotations

import json
from typing import List, Dict

from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import write_artifact
from app.core.timeutil import utc_now


ONTOLOGY_REL_PATH = "graph/ontology.json"


def seed_ontology() -> List[Dict[str, object]]:
    return [
        {"predicate": "mentions", "domain_type": "Document", "range_type": "Entity", "description": "Doc mentions entity"},
        {"predicate": "has_topic", "domain_type": "Document", "range_type": "Topic", "description": "Doc has topic"},
        {"predicate": "related_to", "domain_type": "Entity", "range_type": "Entity", "description": "Entity related to"},
    ]


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])
    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for ontology")

    ontology = seed_ontology()
    write_artifact(source_id, source_version, ONTOLOGY_REL_PATH, json.dumps(ontology, ensure_ascii=True))

    manifest.setdefault("artifacts", {})["ontology"] = ONTOLOGY_REL_PATH
    manifest.setdefault("steps", {})["ontology_seed"] = {"status": "done"}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)
