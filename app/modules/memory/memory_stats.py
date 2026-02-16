"""Memory observability stats for local memory store."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from app.modules.memory.policy import now_iso, now_utc, parse_iso
from app.modules.memory.scope import normalize_scope, scope_matches
from app.queue.db import get_conn


def get_memory_stats(
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, object]:
    scope = normalize_scope(user_id=user_id, project_id=project_id, session_id=session_id)
    rows = _load_memory_rows()
    filtered: List[Dict[str, object]] = []
    for row in rows:
        refs = row.get("source_refs")
        if not scope_matches(refs, scope):
            continue
        filtered.append(row)

    total = len(filtered)
    now = now_utc()
    active = 0
    expired = 0
    by_type: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}

    superseded_items = 0
    supersede_actions = 0
    supersede_links = 0

    feedback_items = 0
    feedback_signals_total = 0
    feedback_cited_total = 0
    feedback_missed_total = 0

    for row in filtered:
        memory_type = str(row.get("memory_type") or "unknown").strip().lower() or "unknown"
        by_type[memory_type] = by_type.get(memory_type, 0) + 1

        refs = row.get("source_refs")
        refs = refs if isinstance(refs, dict) else {}

        memory_kind = str(refs.get("memory_kind") or "").strip().lower()
        if memory_kind in {"semantic", "episodic", "procedural"}:
            by_kind[memory_kind] = by_kind.get(memory_kind, 0) + 1
        else:
            by_kind["unknown"] = by_kind.get("unknown", 0) + 1

        expiry = parse_iso(row.get("expires_at"))
        if expiry is None or now < expiry:
            active += 1
        else:
            expired += 1

        if str(refs.get("superseded_by") or "").strip():
            superseded_items += 1
        supersedes = refs.get("supersedes")
        if isinstance(supersedes, list):
            links = [str(x).strip() for x in supersedes if str(x).strip()]
            if links:
                supersede_actions += 1
                supersede_links += len(set(links))

        if str(refs.get("kind") or "") != "retrieval_feedback":
            continue
        feedback_items += 1
        signals = refs.get("signals")
        if isinstance(signals, list):
            feedback_signals_total += len(signals)
            for signal in signals:
                if not isinstance(signal, dict):
                    continue
                outcome = str(signal.get("outcome") or "").strip().lower()
                if outcome == "cited":
                    feedback_cited_total += 1
                elif outcome == "missed":
                    feedback_missed_total += 1
        else:
            feedback_cited_total += _safe_int(refs.get("cited_count"))
            feedback_missed_total += _safe_int(refs.get("missed_count"))

    supersede_rate = _ratio(superseded_items, total)
    feedback_hit_rate = _ratio(feedback_cited_total, feedback_signals_total)
    return {
        "generated_at": now_iso(),
        "scope": scope,
        "totals": {
            "memory_items": total,
            "active_items": active,
            "expired_items": expired,
        },
        "by_memory_type": dict(sorted(by_type.items())),
        "by_memory_kind": dict(sorted(by_kind.items())),
        "supersede": {
            "superseded_items": superseded_items,
            "supersede_actions": supersede_actions,
            "supersede_link_count": supersede_links,
            "supersede_rate": supersede_rate,
        },
        "retrieval_feedback": {
            "feedback_items": feedback_items,
            "signals_total": feedback_signals_total,
            "cited_signals": feedback_cited_total,
            "missed_signals": feedback_missed_total,
            "hit_rate": feedback_hit_rate,
        },
    }


def _load_memory_rows() -> List[Dict[str, object]]:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute("SELECT memory_type, source_refs, expires_at FROM memory_items")
        else:
            cur.execute("SELECT memory_type, source_refs, expires_at FROM memory_items")
        rows = cur.fetchall()

    out: List[Dict[str, object]] = []
    for row in rows:
        out.append(
            {
                "memory_type": row[0],
                "source_refs": _json_loads(row[1]) or {},
                "expires_at": row[2],
            }
        )
    return out


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


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
