"""Manifest store abstraction."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app.queue.db import get_conn


def get_manifest(source_id: str, source_version: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT manifest_json FROM manifests WHERE source_id=? AND source_version=?" if conn.is_sqlite else
            "SELECT manifest_json FROM manifests WHERE source_id=%s AND source_version=%s",
            (source_id, source_version),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0]) if isinstance(row[0], str) else row[0]


def upsert_manifest(source_id: str, source_version: str, manifest: Dict[str, Any]) -> None:
    payload = json.dumps(manifest)
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "INSERT INTO manifests (source_id, source_version, manifest_json, updated_at) "
                "VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(source_id, source_version) DO UPDATE SET manifest_json=excluded.manifest_json, updated_at=CURRENT_TIMESTAMP",
                (source_id, source_version, payload),
            )
        else:
            cur.execute(
                "INSERT INTO manifests (source_id, source_version, manifest_json, updated_at) "
                "VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (source_id, source_version) DO UPDATE SET manifest_json=EXCLUDED.manifest_json, updated_at=now()",
                (source_id, source_version, payload),
            )
        conn.commit()
