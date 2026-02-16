"""Publish graph artifacts to Snowflake."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.snowflake_client import SnowflakeClient
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run


RECEIPT_REL_PATH = "graph/publish_receipt.json"


def _load_jsonl(text: str) -> List[Dict[str, object]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _lit(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        return f"PARSE_JSON('{json.dumps(value)}')"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _merge_sql(table: str, cols: List[str], rows: List[Dict[str, object]], key_cols: List[str]) -> str:
    if not rows:
        return "-- no rows"
    values = []
    for r in rows:
        values.append([r.get(c.lower()) for c in cols])
    values_sql = ",\n".join("(" + ", ".join([_lit(v) for v in row]) + ")" for row in values)
    return (
        f"MERGE INTO {table} AS t USING (SELECT * FROM VALUES\n{values_sql}\n) AS s({', '.join(cols)}) "
        "ON " + " AND ".join([f"t.{c}=s.{c}" for c in key_cols]) + " "
        "WHEN MATCHED THEN UPDATE SET "
        + ", ".join([f"t.{c}=s.{c}" for c in cols])
        + " WHEN NOT MATCHED THEN INSERT (" + ", ".join(cols) + ") VALUES (" + ", ".join([f"s.{c}" for c in cols]) + ");"
    )


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for publish_graph")

    ent_rel = manifest.get("artifacts", {}).get("graph_entities")
    rel_rel = manifest.get("artifacts", {}).get("graph_relations")
    clm_rel = manifest.get("artifacts", {}).get("graph_claims")
    ont_rel = manifest.get("artifacts", {}).get("ontology")

    if not (ent_rel and rel_rel and clm_rel and ont_rel):
        raise RuntimeError("Graph artifacts missing")

    ent_text = read_artifact(source_id, source_version, str(ent_rel))
    rel_text = read_artifact(source_id, source_version, str(rel_rel))
    clm_text = read_artifact(source_id, source_version, str(clm_rel))
    ont_text = read_artifact(source_id, source_version, str(ont_rel))

    if ent_text is None or rel_text is None or clm_text is None or ont_text is None:
        raise RuntimeError("Graph artifacts missing on disk")

    entities = _load_jsonl(ent_text)
    relations = _load_jsonl(rel_text)
    claims = _load_jsonl(clm_text)
    ontology = json.loads(ont_text)

    ent_sql = _merge_sql(
        "ENTITIES",
        ["ENTITY_ID", "NAME", "TYPE", "ALIASES", "METADATA", "UPDATED_AT"],
        [
            {
                "entity_id": e.get("entity_id"),
                "name": e.get("name"),
                "type": e.get("type"),
                "aliases": e.get("aliases", []),
                "metadata": e.get("metadata", {}),
                "updated_at": utc_now().isoformat(),
            }
            for e in entities
        ],
        ["ENTITY_ID"],
    )

    rel_sql = _merge_sql(
        "RELATIONS",
        [
            "REL_ID",
            "SUBJ_ENTITY_ID",
            "PREDICATE",
            "OBJ_ENTITY_ID",
            "DOC_ID",
            "SEGMENT_ID",
            "CONFIDENCE",
            "UPDATED_AT",
        ],
        [
            {
                "rel_id": r.get("rel_id"),
                "subj_entity_id": r.get("subj_entity_id"),
                "predicate": r.get("predicate"),
                "obj_entity_id": r.get("obj_entity_id"),
                "doc_id": r.get("doc_id"),
                "segment_id": r.get("segment_id"),
                "confidence": r.get("confidence", 0.5),
                "updated_at": utc_now().isoformat(),
            }
            for r in relations
        ],
        ["REL_ID"],
    )

    clm_sql = _merge_sql(
        "CLAIMS",
        ["CLAIM_ID", "CLAIM_TEXT", "DOC_ID", "SEGMENT_ID", "CONFIDENCE", "UPDATED_AT"],
        [
            {
                "claim_id": c.get("claim_id"),
                "claim_text": c.get("claim_text"),
                "doc_id": c.get("doc_id"),
                "segment_id": c.get("segment_id"),
                "confidence": c.get("confidence", 0.5),
                "updated_at": utc_now().isoformat(),
            }
            for c in claims
        ],
        ["CLAIM_ID"],
    )

    ont_sql = _merge_sql(
        "ONTOLOGY",
        ["PREDICATE", "DOMAIN_TYPE", "RANGE_TYPE", "DESCRIPTION", "UPDATED_AT"],
        [
            {
                "predicate": o.get("predicate"),
                "domain_type": o.get("domain_type"),
                "range_type": o.get("range_type"),
                "description": o.get("description"),
                "updated_at": utc_now().isoformat(),
            }
            for o in ontology
        ],
        ["PREDICATE", "DOMAIN_TYPE", "RANGE_TYPE"],
    )

    receipt = {
        "entities_sql": ent_sql,
        "relations_sql": rel_sql,
        "claims_sql": clm_sql,
        "ontology_sql": ont_sql,
        "error": None,
    }

    run_id = log_run(
        lane="io",
        component="graph_publish",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    try:
        client = SnowflakeClient()
        client.execute_sql(ent_sql)
        client.execute_sql(rel_sql)
        client.execute_sql(clm_sql)
        client.execute_sql(ont_sql)
    except Exception as exc:
        receipt["error"] = str(exc)

    write_artifact(source_id, source_version, RECEIPT_REL_PATH, json.dumps(receipt, ensure_ascii=True))
    manifest.setdefault("artifacts", {})["graph_publish_receipt"] = RECEIPT_REL_PATH
    manifest.setdefault("steps", {})["graph_publish"] = {"status": "done" if receipt["error"] is None else "failed"}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane="io",
        component="graph_publish",
        input_json={"run_id": run_id},
        output_json={"error": receipt["error"]},
        error=receipt["error"],
    )
