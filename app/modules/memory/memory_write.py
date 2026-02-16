"""Memory write module for session/working/long-term memory."""

from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional

from app.clients.snowflake_client import SnowflakeClient, merge_memory_sql
from app.modules.memory.policy import (
    clamp_float,
    default_expiry,
    normalize_list,
    normalize_memory_type,
    normalize_text,
    now_iso,
    now_utc,
    parse_iso,
)
from app.modules.memory.router import normalize_memory_kind, route_memory
from app.queue.db import get_conn
from app.queue.logs import log_run


MemoryType = str


def write_memory(
    memory_type: MemoryType,
    text: str,
    topics: Optional[List[str]] = None,
    entities: Optional[List[str]] = None,
    source_refs: Optional[Dict[str, object]] = None,
    importance: float = 0.5,
    confidence: float = 0.7,
    expires_at: Optional[str] = None,
    pinned_until: Optional[str] = None,
    publish_long_term: bool = False,
    memory_kind: Optional[str] = None,
    memory_slot: Optional[str] = None,
    memory_value: Optional[str] = None,
    overwrite_conflicts: bool = False,
) -> Dict[str, object]:
    memory_id = str(uuid.uuid4())
    memory_type = normalize_memory_type(memory_type)
    text = normalize_text(text)
    topics = normalize_list(topics)
    entities = normalize_list(entities)
    source_refs = dict(source_refs or {})
    route = route_memory(text=text, memory_type_hint=memory_type, preferred_kind=memory_kind)
    memory_kind = normalize_memory_kind(memory_kind, default=str(route.get("memory_kind") or "semantic"))
    memory_slot = normalize_text(memory_slot or route.get("memory_slot") or "", max_len=64) or None
    memory_value = normalize_text(memory_value or route.get("memory_value") or "", max_len=280) or None
    source_refs.setdefault("memory_kind", memory_kind)
    source_refs.setdefault("memory_router_reason", str(route.get("reason") or ""))
    source_refs.setdefault("memory_router_confidence", float(route.get("confidence") or 0.0))
    if memory_slot:
        source_refs.setdefault("memory_slot", memory_slot)
    if memory_value:
        source_refs.setdefault("memory_value", memory_value)
    created_at_dt = now_utc()
    created_at = created_at_dt.isoformat()
    importance = clamp_float(importance, default=0.5)
    confidence = clamp_float(confidence, default=0.7)
    expiry = parse_iso(expires_at)
    expires_at = expiry.isoformat() if expiry else default_expiry(memory_type, created_at_dt)
    pin_dt = parse_iso(pinned_until)
    pinned_until = pin_dt.isoformat() if pin_dt else None

    with get_conn() as conn:
        cur = conn.cursor()
        inserted = False
        if conn.is_sqlite:
            try:
                cur.execute(
                    "INSERT INTO memory_items (memory_id, memory_type, text, topics, entities, source_refs, "
                    "importance, confidence, access_count, last_accessed_at, expires_at, pinned_until, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (
                        memory_id,
                        memory_type,
                        text,
                        _json_dumps(topics),
                        _json_dumps(entities),
                        _json_dumps(source_refs),
                        importance,
                        confidence,
                        created_at,
                        expires_at,
                        pinned_until,
                    ),
                )
                inserted = True
            except Exception:
                inserted = False
            if not inserted:
                cur.execute(
                    "INSERT INTO memory_items (memory_id, memory_type, text, topics, entities, source_refs, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    (
                        memory_id,
                        memory_type,
                        text,
                        _json_dumps(topics),
                        _json_dumps(entities),
                        _json_dumps(source_refs),
                    ),
                )
        else:
            try:
                cur.execute(
                    "INSERT INTO memory_items (memory_id, memory_type, text, topics, entities, source_refs, "
                    "importance, confidence, access_count, last_accessed_at, expires_at, pinned_until, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, now())",
                    (
                        memory_id,
                        memory_type,
                        text,
                        _json_dumps(topics),
                        _json_dumps(entities),
                        _json_dumps(source_refs),
                        importance,
                        confidence,
                        created_at,
                        expires_at,
                        pinned_until,
                    ),
                )
                inserted = True
            except Exception:
                inserted = False
            if not inserted:
                cur.execute(
                    "INSERT INTO memory_items (memory_id, memory_type, text, topics, entities, source_refs, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, now())",
                    (
                        memory_id,
                        memory_type,
                        text,
                        _json_dumps(topics),
                        _json_dumps(entities),
                        _json_dumps(source_refs),
                    ),
                )
        conn.commit()

    superseded_count = 0
    if overwrite_conflicts and memory_slot and memory_value:
        superseded_count = _supersede_conflicting_memories(
            memory_id=memory_id,
            memory_slot=memory_slot,
            memory_value=memory_value,
            memory_kind=memory_kind,
        )

    receipt = {
        "memory_id": memory_id,
        "memory_type": memory_type,
        "memory_kind": memory_kind,
        "superseded_count": superseded_count,
        "published": False,
        "error": None,
    }

    run_id = log_run(
        lane="io",
        component="memory_write",
        input_json={"memory_id": memory_id, "memory_type": memory_type},
    )

    if publish_long_term:
        row = {
            "memory_id": memory_id,
            "category": memory_type,
            "text": text,
            "topics": topics,
            "entities": entities,
            "source_refs": source_refs,
            "created_at": created_at,
        }
        sql = merge_memory_sql([row])
        try:
            client = SnowflakeClient()
            client.execute_sql(sql)
            receipt["published"] = True
        except Exception as exc:
            receipt["error"] = str(exc)
            receipt["sql"] = sql

    log_run(
        lane="io",
        component="memory_write",
        input_json={"run_id": run_id},
        output_json=receipt,
        error=receipt.get("error"),
    )

    return receipt


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=True)


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


def _supersede_conflicting_memories(
    memory_id: str,
    memory_slot: str,
    memory_value: str,
    memory_kind: str,
) -> int:
    like_pattern = f'%\"memory_slot\"%{memory_slot}%'
    updates: List[tuple[str, str]] = []
    now = now_iso()
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT memory_id, source_refs FROM memory_items "
                "WHERE memory_id <> ? AND source_refs LIKE ? ORDER BY created_at DESC LIMIT 60",
                (memory_id, like_pattern),
            )
        else:
            cur.execute(
                "SELECT memory_id, source_refs FROM memory_items "
                "WHERE memory_id <> %s AND CAST(source_refs AS TEXT) ILIKE %s ORDER BY created_at DESC LIMIT 60",
                (memory_id, like_pattern),
            )

        rows = cur.fetchall()
        for row in rows:
            old_id = str(row[0] or "")
            refs = _json_loads(row[1]) or {}
            if not isinstance(refs, dict):
                continue
            if str(refs.get("memory_slot") or "") != memory_slot:
                continue
            if str(refs.get("memory_kind") or "semantic") != memory_kind:
                continue
            previous_value = normalize_text(refs.get("memory_value") or "", max_len=280)
            if not previous_value or previous_value == memory_value:
                continue
            refs["superseded_by"] = memory_id
            refs["superseded_at"] = now
            updates.append((old_id, _json_dumps(refs)))

        for old_id, refs_json in updates:
            try:
                if conn.is_sqlite:
                    cur.execute(
                        "UPDATE memory_items SET source_refs=?, expires_at=? WHERE memory_id=?",
                        (refs_json, now, old_id),
                    )
                else:
                    cur.execute(
                        "UPDATE memory_items SET source_refs=%s, expires_at=%s WHERE memory_id=%s",
                        (refs_json, now, old_id),
                    )
            except Exception:
                # Older schemas may not have expires_at; keep supersede metadata anyway.
                if conn.is_sqlite:
                    cur.execute("UPDATE memory_items SET source_refs=? WHERE memory_id=?", (refs_json, old_id))
                else:
                    cur.execute("UPDATE memory_items SET source_refs=%s WHERE memory_id=%s", (refs_json, old_id))

        if updates:
            conn.commit()
    return len(updates)
