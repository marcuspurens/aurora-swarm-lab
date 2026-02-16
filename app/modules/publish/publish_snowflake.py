"""Publish artifacts to Snowflake."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import json
from datetime import datetime, timezone

from app.clients.snowflake_client import SnowflakeClient, merge_documents_sql, merge_segments_sql
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run


def publish_documents(rows: List[Dict[str, Any]], client: Optional[SnowflakeClient] = None, dry_run: bool = True) -> str:
    sql = merge_documents_sql(rows)
    if dry_run:
        return sql
    client = client or SnowflakeClient()
    client.execute_sql(sql)
    return sql


def publish_segments(rows: List[Dict[str, Any]], client: Optional[SnowflakeClient] = None, dry_run: bool = True) -> str:
    sql = merge_segments_sql(rows)
    if dry_run:
        return sql
    client = client or SnowflakeClient()
    client.execute_sql(sql)
    return sql


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(text: str) -> List[Dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def handle_job(job: Dict[str, Any]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for publish_snowflake")

    run_id = log_run(
        lane=str(job.get("lane", "io")),
        component="publish_snowflake",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    summary_rel = manifest.get("artifacts", {}).get("doc_summary")
    summary = {}
    if summary_rel:
        summary_text = read_artifact(source_id, source_version, str(summary_rel))
        if summary_text:
            summary = json.loads(summary_text)

    doc_row = {
        "doc_id": source_id,
        "source_id": source_id,
        "source_version": source_version,
        "source_type": manifest.get("source_type"),
        "source_uri": manifest.get("source_uri"),
        "title": manifest.get("title"),
        "language": manifest.get("language"),
        "summary_short": summary.get("summary_short", ""),
        "summary_long": summary.get("summary_long", ""),
        "metadata": manifest.get("metadata", {}),
        "created_at": manifest.get("updated_at") or _now_iso(),
    }

    chunks_rel = (
        manifest.get("artifacts", {}).get("enriched_chunks")
        or manifest.get("artifacts", {}).get("chunks")
    )
    if not chunks_rel:
        raise RuntimeError("chunks artifact not found for publish")

    chunk_text = read_artifact(source_id, source_version, str(chunks_rel))
    if chunk_text is None:
        raise RuntimeError("chunks artifact missing on disk")

    chunks = _load_jsonl(chunk_text)
    segment_rows = []
    for c in chunks:
        segment_rows.append(
            {
                "doc_id": c.get("doc_id") or source_id,
                "segment_id": c.get("segment_id"),
                "start_ms": c.get("start_ms"),
                "end_ms": c.get("end_ms"),
                "speaker": c.get("speaker"),
                "text": c.get("text", ""),
                "topics": c.get("topics", []),
                "entities": c.get("entities", []),
                "source_refs": c.get("source_refs", {}),
                "updated_at": _now_iso(),
            }
        )

    sql_docs = publish_documents([doc_row], dry_run=True)
    sql_segments = publish_segments(segment_rows, dry_run=True)

    receipt = {
        "doc_sql": sql_docs,
        "segments_sql": sql_segments,
        "dry_run": True,
        "error": None,
        "published_at": utc_now().isoformat(),
    }

    try:
        client = SnowflakeClient()
        publish_documents([doc_row], client=client, dry_run=False)
        publish_segments(segment_rows, client=client, dry_run=False)
        receipt["dry_run"] = False
    except Exception as exc:
        receipt["error"] = str(exc)

    write_artifact(source_id, source_version, "publish/snowflake_receipt.json", json.dumps(receipt, ensure_ascii=True))
    manifest.setdefault("artifacts", {})["snowflake_receipt"] = "publish/snowflake_receipt.json"
    manifest.setdefault("steps", {})["publish_snowflake"] = {
        "status": "done" if receipt["error"] is None else "failed",
    }
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "io")),
        component="publish_snowflake",
        input_json={"run_id": run_id},
        output_json={"dry_run": receipt["dry_run"], "error": receipt["error"]},
        error=receipt["error"],
    )
