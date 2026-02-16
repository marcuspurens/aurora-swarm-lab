"""Background maintenance for memory lifecycle hygiene."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from app.core.config import load_settings
from app.modules.memory.policy import now_iso, now_utc, parse_iso
from app.modules.memory.scope import normalize_scope, scope_from_source_refs, scope_matches
from app.queue.db import get_conn
from app.queue.logs import log_run


def run_memory_maintenance(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, object]:
    settings = load_settings()
    scope = normalize_scope(user_id=user_id, project_id=project_id, session_id=session_id)
    now = now_utc()
    feedback_cutoff = now - timedelta(days=int(settings.memory_maintenance_feedback_retention_days))

    rows = _load_rows()
    scanned = 0
    delete_expired: List[str] = []
    feedback_rows: List[Tuple[str, object, Dict[str, object]]] = []
    delete_feedback_old: List[str] = []
    max_deletes = max(10, int(settings.memory_maintenance_max_delete_per_run))

    for memory_id, source_refs, created_at, expires_at, pinned_until in rows:
        refs = _json_loads(source_refs) or {}
        refs = refs if isinstance(refs, dict) else {}
        if not scope_matches(refs, scope):
            continue
        scanned += 1

        if _is_expired_and_not_pinned(expires_at=expires_at, pinned_until=pinned_until, now=now):
            delete_expired.append(memory_id)
            continue

        if str(refs.get("kind") or "") != "retrieval_feedback":
            continue
        feedback_rows.append((memory_id, created_at, refs))
        created_dt = parse_iso(created_at)
        if created_dt is not None and created_dt < feedback_cutoff:
            delete_feedback_old.append(memory_id)

    # Keep latest feedback history window to bound drift/size even when old items are recent.
    overflow_ids = _feedback_overflow_ids(
        feedback_rows=feedback_rows,
        keep_limit=max(1, int(settings.retrieval_feedback_history_limit)),
    )

    # Preserve order of reasons, de-duplicate IDs, and cap total delete budget per run.
    deleted_reasons: Dict[str, str] = {}
    for memory_id in delete_expired:
        deleted_reasons.setdefault(memory_id, "expired")
    for memory_id in delete_feedback_old:
        deleted_reasons.setdefault(memory_id, "feedback_retention")
    for memory_id in overflow_ids:
        deleted_reasons.setdefault(memory_id, "feedback_overflow")

    all_delete_ids = list(deleted_reasons.keys())[:max_deletes]
    _delete_rows(all_delete_ids)

    deleted_breakdown = {"expired": 0, "feedback_retention": 0, "feedback_overflow": 0}
    for memory_id in all_delete_ids:
        reason = deleted_reasons.get(memory_id) or "expired"
        deleted_breakdown[reason] = int(deleted_breakdown.get(reason) or 0) + 1

    return {
        "generated_at": now_iso(),
        "scope": scope,
        "scanned_items": scanned,
        "deleted_total": len(all_delete_ids),
        "deleted_breakdown": deleted_breakdown,
        "feedback_retention_days": int(settings.memory_maintenance_feedback_retention_days),
        "feedback_keep_limit": int(settings.retrieval_feedback_history_limit),
        "max_delete_per_run": max_deletes,
    }


def handle_job(job: Dict[str, object]) -> None:
    lane = str(job.get("lane") or "io")
    run_id = log_run(
        lane=lane,
        component="memory_maintain",
        input_json={
            "source_id": str(job.get("source_id") or ""),
            "source_version": str(job.get("source_version") or ""),
        },
    )
    try:
        output = run_memory_maintenance()
        log_run(lane=lane, component="memory_maintain", input_json={"run_id": run_id}, output_json=output)
    except Exception as exc:
        log_run(lane=lane, component="memory_maintain", input_json={"run_id": run_id}, error=str(exc))
        raise


def _load_rows() -> List[Tuple[str, object, object, object, object]]:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT memory_id, source_refs, created_at, expires_at, pinned_until "
                "FROM memory_items ORDER BY created_at DESC"
            )
        else:
            cur.execute(
                "SELECT memory_id, source_refs, created_at, expires_at, pinned_until "
                "FROM memory_items ORDER BY created_at DESC"
            )
        rows = cur.fetchall()
    out: List[Tuple[str, object, object, object, object]] = []
    for row in rows:
        out.append((str(row[0] or ""), row[1], row[2], row[3], row[4]))
    return out


def _feedback_overflow_ids(
    feedback_rows: List[Tuple[str, object, Dict[str, object]]],
    keep_limit: int,
) -> List[str]:
    if not feedback_rows:
        return []
    # Rows are globally sorted by created_at DESC from _load_rows.
    # Keep the newest N feedback items per scope to avoid cross-tenant pruning.
    seen_by_scope: Dict[str, int] = {}
    overflow: List[str] = []
    for memory_id, _created_at, refs in feedback_rows:
        scope = scope_from_source_refs(refs)
        scope_key = "|".join(
            [
                str(scope.get("user_id") or ""),
                str(scope.get("project_id") or ""),
                str(scope.get("session_id") or ""),
            ]
        )
        seen = int(seen_by_scope.get(scope_key) or 0)
        if seen >= keep_limit:
            if str(memory_id).strip():
                overflow.append(str(memory_id))
            continue
        seen_by_scope[scope_key] = seen + 1
    return overflow


def _delete_rows(memory_ids: List[str]) -> None:
    ids = [str(x).strip() for x in memory_ids if str(x).strip()]
    if not ids:
        return
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            placeholders = ", ".join(["?"] * len(ids))
            cur.execute(f"DELETE FROM memory_items WHERE memory_id IN ({placeholders})", tuple(ids))
        else:
            placeholders = ", ".join(["%s"] * len(ids))
            cur.execute(f"DELETE FROM memory_items WHERE memory_id IN ({placeholders})", tuple(ids))
        conn.commit()


def _is_expired_and_not_pinned(expires_at: object, pinned_until: object, now: object) -> bool:
    expiry = parse_iso(expires_at)
    if expiry is None:
        return False
    pin = parse_iso(pinned_until)
    if pin is not None and now <= pin:
        return False
    return now >= expiry


def _json_loads(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return None
