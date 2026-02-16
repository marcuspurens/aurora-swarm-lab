"""Memory recall module for session/working/long-term memory."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from app.clients.snowflake_client import SnowflakeClient
from app.modules.memory.policy import (
    TYPE_WEIGHT,
    clamp_float,
    normalize_memory_type,
    now_iso,
    now_utc,
    overlap_score,
    parse_iso,
    recency_score,
    tokens,
)
from app.modules.memory.scope import normalize_scope, scope_matches
from app.queue.db import get_conn


def recall(
    query: str,
    limit: int = 10,
    memory_type: Optional[str] = None,
    memory_kind: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    include_long_term: bool = False,
    client: Optional[SnowflakeClient] = None,
) -> List[Dict[str, object]]:
    q = str(query or "").strip()
    if not q:
        return []

    q_tokens = tokens(q)
    candidate_limit = max(limit * 5, 20)
    scope = normalize_scope(user_id=user_id, project_id=project_id, session_id=session_id)
    local = _query_local(q, memory_type=memory_type, limit=candidate_limit)
    if scope:
        local = [item for item in local if _scope_matches(item, scope)]
    memory_kind = _normalize_memory_kind_filter(memory_kind)
    if memory_kind:
        local = [item for item in local if _memory_kind_matches(item, memory_kind)]

    ranked_local: List[Dict[str, object]] = []
    for item in local:
        if _is_expired(item):
            continue
        score = _score_local_item(item, q_tokens)
        item["recall_score"] = score
        ranked_local.append(item)
    ranked_local.sort(key=lambda r: float(r.get("recall_score", 0.0)), reverse=True)
    selected_local = ranked_local[:limit]
    _touch_local([str(item.get("memory_id")) for item in selected_local if item.get("memory_id")])

    if include_long_term:
        remote = _query_long_term(
            q,
            limit=limit,
            client=client,
            memory_type=memory_type,
            memory_kind=memory_kind,
            scope=scope,
        )
        if scope:
            remote = [item for item in remote if _scope_matches(item, scope)]
        if memory_kind:
            remote = [item for item in remote if _memory_kind_matches(item, memory_kind)]
        for item in remote:
            item["recall_score"] = _score_remote_item(item, q_tokens)
        selected_local.extend(remote)
        selected_local.sort(key=lambda r: float(r.get("recall_score", 0.0)), reverse=True)

    return selected_local[:limit]


def _query_local(query: str, memory_type: Optional[str], limit: int) -> List[Dict[str, object]]:
    like_query = f"%{query}%"
    params: List[object]
    if memory_type:
        normalized_type = normalize_memory_type(memory_type)
        where_sql = "memory_type=? AND (text LIKE ? OR topics LIKE ? OR entities LIKE ?)"
        params = [normalized_type, like_query, like_query, like_query, limit]
    else:
        where_sql = "text LIKE ? OR topics LIKE ? OR entities LIKE ?"
        params = [like_query, like_query, like_query, limit]

    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            sql_new = (
                "SELECT memory_id, memory_type, text, topics, entities, source_refs, created_at, "
                "importance, confidence, access_count, last_accessed_at, expires_at, pinned_until "
                f"FROM memory_items WHERE ({where_sql}) LIMIT ?"
            )
            sql_old = (
                "SELECT memory_id, memory_type, text, topics, entities, source_refs, created_at "
                f"FROM memory_items WHERE ({where_sql}) LIMIT ?"
            )
        else:
            where_sql_pg = where_sql.replace("?", "%s").replace("LIKE", "ILIKE")
            sql_new = (
                "SELECT memory_id, memory_type, text, topics, entities, source_refs, created_at, "
                "importance, confidence, access_count, last_accessed_at, expires_at, pinned_until "
                f"FROM memory_items WHERE ({where_sql_pg}) LIMIT %s"
            )
            sql_old = (
                "SELECT memory_id, memory_type, text, topics, entities, source_refs, created_at "
                f"FROM memory_items WHERE ({where_sql_pg}) LIMIT %s"
            )

        try:
            cur.execute(sql_new, tuple(params))
            rows = cur.fetchall()
            return [_row_to_item(row, has_policy_fields=True) for row in rows]
        except Exception:
            cur.execute(sql_old, tuple(params))
            rows = cur.fetchall()
            return [_row_to_item(row, has_policy_fields=False) for row in rows]


def _row_to_item(row: object, has_policy_fields: bool) -> Dict[str, object]:
    topics = _json_loads(row[3]) or []
    entities = _json_loads(row[4]) or []
    source_refs = _json_loads(row[5]) or {}
    memory_kind = None
    if isinstance(source_refs, dict):
        memory_kind = source_refs.get("memory_kind")
    item: Dict[str, object] = {
        "memory_id": row[0],
        "memory_type": row[1],
        "memory_kind": memory_kind,
        "text": row[2],
        "topics": topics if isinstance(topics, list) else [],
        "entities": entities if isinstance(entities, list) else [],
        "source_refs": source_refs if isinstance(source_refs, dict) else {},
        "created_at": row[6],
        "source": "local",
    }
    if has_policy_fields:
        item.update(
            {
                "importance": clamp_float(row[7], default=0.5),
                "confidence": clamp_float(row[8], default=0.7),
                "access_count": int(row[9] or 0),
                "last_accessed_at": row[10],
                "expires_at": row[11],
                "pinned_until": row[12],
            }
        )
    else:
        item.update(
            {
                "importance": 0.5,
                "confidence": 0.7,
                "access_count": 0,
                "last_accessed_at": None,
                "expires_at": None,
                "pinned_until": None,
            }
        )
    return item


def _query_long_term(
    query: str,
    limit: int,
    client: Optional[SnowflakeClient],
    memory_type: Optional[str],
    memory_kind: Optional[str],
    scope: Dict[str, str],
) -> List[Dict[str, object]]:
    client = client or SnowflakeClient()
    sql = client.search_memory(
        query,
        limit=limit,
        filters={
            "memory_type": normalize_memory_type(memory_type) if memory_type else None,
            "memory_kind": memory_kind,
            **scope,
        },
    )
    try:
        rows = client.execute_query(sql)
    except Exception:
        rows = []
    out: List[Dict[str, object]] = []
    for row in rows:
        out.append(
            {
                "memory_id": row.get("memory_id"),
                "memory_type": normalize_memory_type(row.get("category") or "long_term"),
                "memory_kind": _read_memory_kind(row.get("source_refs")),
                "text": row.get("text"),
                "topics": row.get("topics") if isinstance(row.get("topics"), list) else [],
                "entities": row.get("entities") if isinstance(row.get("entities"), list) else [],
                "source_refs": row.get("source_refs") if isinstance(row.get("source_refs"), dict) else {},
                "created_at": row.get("created_at"),
                "importance": 0.7,
                "confidence": 0.7,
                "access_count": 0,
                "last_accessed_at": None,
                "expires_at": None,
                "pinned_until": None,
                "source": "snowflake",
            }
        )
    return out


def _score_local_item(item: Dict[str, object], query_tokens: List[str]) -> float:
    text_score = overlap_score(query_tokens, item.get("text"))
    topic_score = overlap_score(query_tokens, " ".join(item.get("topics") or []))
    entity_score = overlap_score(query_tokens, " ".join(item.get("entities") or []))
    meta_score = max(topic_score, entity_score)
    recent = recency_score(item.get("created_at"))
    importance = clamp_float(item.get("importance"), default=0.5)
    confidence = clamp_float(item.get("confidence"), default=0.7)
    type_weight = TYPE_WEIGHT.get(normalize_memory_type(item.get("memory_type")), 0.9)
    access_count = int(item.get("access_count") or 0)
    access_bonus = min(access_count, 20) / 200.0
    pin_bonus = 0.05 if _is_pinned(item) else 0.0
    raw = (
        (0.50 * text_score)
        + (0.20 * meta_score)
        + (0.15 * recent)
        + (0.10 * importance)
        + (0.05 * confidence)
    )
    return round((raw * type_weight) + access_bonus + pin_bonus, 6)


def _score_remote_item(item: Dict[str, object], query_tokens: List[str]) -> float:
    text_score = overlap_score(query_tokens, item.get("text"))
    type_weight = TYPE_WEIGHT.get(normalize_memory_type(item.get("memory_type")), 0.8)
    return round((0.65 * text_score + 0.35 * recency_score(item.get("created_at"))) * type_weight, 6)


def _touch_local(memory_ids: List[str]) -> None:
    if not memory_ids:
        return
    placeholders_sqlite = ", ".join(["?"] * len(memory_ids))
    placeholders_pg = ", ".join(["%s"] * len(memory_ids))
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            if conn.is_sqlite:
                cur.execute(
                    f"UPDATE memory_items SET access_count=COALESCE(access_count, 0)+1, last_accessed_at=? "
                    f"WHERE memory_id IN ({placeholders_sqlite})",
                    tuple([now_iso()] + memory_ids),
                )
            else:
                cur.execute(
                    f"UPDATE memory_items SET access_count=COALESCE(access_count, 0)+1, last_accessed_at=%s "
                    f"WHERE memory_id IN ({placeholders_pg})",
                    tuple([now_iso()] + memory_ids),
                )
            conn.commit()
        except Exception:
            pass


def _is_expired(item: Dict[str, object]) -> bool:
    expiry = parse_iso(item.get("expires_at"))
    if expiry is None:
        return False
    return now_utc() >= expiry


def _is_pinned(item: Dict[str, object]) -> bool:
    pinned_until = parse_iso(item.get("pinned_until"))
    if pinned_until is None:
        return False
    return now_utc() <= pinned_until


def _json_loads(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    return value


def _normalize_memory_kind_filter(value: object) -> Optional[str]:
    candidate = str(value or "").strip().lower()
    if candidate in {"semantic", "episodic", "procedural"}:
        return candidate
    return None


def _memory_kind_matches(item: Dict[str, object], memory_kind: str) -> bool:
    return str(item.get("memory_kind") or "").strip().lower() == memory_kind


def _scope_matches(item: Dict[str, object], scope: Dict[str, str]) -> bool:
    return scope_matches(item.get("source_refs"), scope)


def _read_memory_kind(source_refs: object) -> Optional[str]:
    if not isinstance(source_refs, dict):
        return None
    value = str(source_refs.get("memory_kind") or "").strip().lower()
    if value in {"semantic", "episodic", "procedural"}:
        return value
    return None
