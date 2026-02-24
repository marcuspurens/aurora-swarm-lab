"""List all ingested sources from the library."""

from __future__ import annotations

import json
from typing import Any

from app.queue.db import get_conn


def _derive_status(manifest_json: str) -> str:
    """Derive pipeline status from manifest_json steps dict."""
    try:
        manifest: dict[str, Any] = json.loads(manifest_json) if isinstance(manifest_json, str) else manifest_json
    except (json.JSONDecodeError, TypeError):
        return "partial"

    steps: dict[str, Any] = manifest.get("steps", {})
    if not isinstance(steps, dict):
        return "partial"

    embed_done = any(
        "embed" in key and isinstance(v, dict) and v.get("status") == "done"
        for key, v in steps.items()
    )
    chunk_done = any(
        "chunk" in key and isinstance(v, dict) and v.get("status") == "done"
        for key, v in steps.items()
    )
    ingest_done = any(
        "ingest" in key and isinstance(v, dict) and v.get("status") == "done"
        for key, v in steps.items()
    )

    if embed_done:
        return "embeddings done"
    if chunk_done:
        return "chunks done"
    if ingest_done:
        return "ingest done"
    return "partial"


def _derive_chunk_count(manifest_json: str) -> int:
    """Derive chunk count from manifest_json."""
    try:
        manifest: dict[str, Any] = json.loads(manifest_json) if isinstance(manifest_json, str) else manifest_json
    except (json.JSONDecodeError, TypeError):
        return 0

    if "chunk_count" in manifest:
        try:
            return int(manifest["chunk_count"])
        except (ValueError, TypeError):
            pass

    steps = manifest.get("steps", {})
    if isinstance(steps, dict):
        return len(steps)
    return 0


def list_sources() -> list[dict[str, Any]]:
    """Query the library and return a list of source summaries."""
    with get_conn() as conn:
        cur = conn.cursor()

        # Get all manifests ordered by updated_at DESC
        cur.execute(
            "SELECT source_id, source_version, manifest_json, updated_at "
            "FROM manifests ORDER BY updated_at DESC"
        )
        rows = cur.fetchall()

        # Group by source_id, keeping the latest (first encountered) per source
        seen: dict[str, dict[str, Any]] = {}
        for row in rows:
            sid = row[0]
            if sid not in seen:
                seen[sid] = {
                    "source_id": sid,
                    "source_version": row[1],
                    "manifest_json": row[2],
                    "updated_at": row[3],
                }

        results: list[dict[str, Any]] = []
        ph = "?" if conn.is_sqlite else "%s"

        for sid, info in seen.items():
            # Count embeddings
            cur.execute(
                f"SELECT COUNT(*) FROM embeddings WHERE source_id = {ph}",
                (sid,),
            )
            embed_count: int = cur.fetchone()[0]

            # Check for failed jobs
            cur.execute(
                f"SELECT COUNT(*) FROM jobs WHERE source_id = {ph} AND status = 'failed'",
                (sid,),
            )
            failed_count: int = cur.fetchone()[0]

            status = _derive_status(info["manifest_json"])
            if failed_count > 0:
                status = "failed"

            chunks = _derive_chunk_count(info["manifest_json"])

            results.append({
                "source_id": sid,
                "date": info["updated_at"] or "",
                "chunks": chunks,
                "embeddings": embed_count,
                "status": status,
            })

        return results
