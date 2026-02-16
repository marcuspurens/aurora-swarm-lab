"""Embedding storage and retrieval helpers."""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.queue.db import get_conn


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=True)


def _json_loads(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def get_embedding_hashes(doc_id: str) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute("SELECT segment_id, text_hash FROM embeddings WHERE doc_id=?", (doc_id,))
        else:
            cur.execute("SELECT segment_id, text_hash FROM embeddings WHERE doc_id=%s", (doc_id,))
        for row in cur.fetchall():
            segment_id = row[0]
            text_hash = row[1]
            if segment_id and text_hash:
                hashes[str(segment_id)] = str(text_hash)
    return hashes


def upsert_embedding(row: Dict[str, Any]) -> None:
    payload = {
        "doc_id": row["doc_id"],
        "segment_id": row["segment_id"],
        "source_id": row["source_id"],
        "source_version": row["source_version"],
        "text": row["text"],
        "text_hash": row["text_hash"],
        "embedding": _json_dumps(row["embedding"]),
        "start_ms": row.get("start_ms"),
        "end_ms": row.get("end_ms"),
        "speaker": row.get("speaker"),
        "source_refs": _json_dumps(row.get("source_refs") or {}),
    }
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "INSERT INTO embeddings (doc_id, segment_id, source_id, source_version, text, text_hash, embedding, start_ms, end_ms, speaker, source_refs, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(doc_id, segment_id) DO UPDATE SET "
                "source_id=excluded.source_id, source_version=excluded.source_version, text=excluded.text, text_hash=excluded.text_hash, "
                "embedding=excluded.embedding, start_ms=excluded.start_ms, end_ms=excluded.end_ms, speaker=excluded.speaker, "
                "source_refs=excluded.source_refs, updated_at=CURRENT_TIMESTAMP",
                tuple(payload.values()),
            )
        else:
            cur.execute(
                "INSERT INTO embeddings (doc_id, segment_id, source_id, source_version, text, text_hash, embedding, start_ms, end_ms, speaker, source_refs, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (doc_id, segment_id) DO UPDATE SET "
                "source_id=EXCLUDED.source_id, source_version=EXCLUDED.source_version, text=EXCLUDED.text, text_hash=EXCLUDED.text_hash, "
                "embedding=EXCLUDED.embedding, start_ms=EXCLUDED.start_ms, end_ms=EXCLUDED.end_ms, speaker=EXCLUDED.speaker, "
                "source_refs=EXCLUDED.source_refs, updated_at=now()",
                tuple(payload.values()),
            )
        conn.commit()


def _cosine(a: Iterable[float], b: Iterable[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _load_embeddings() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT doc_id, segment_id, start_ms, end_ms, speaker, text, embedding, source_refs FROM embeddings"
            )
        else:
            cur.execute(
                "SELECT doc_id, segment_id, start_ms, end_ms, speaker, text, embedding, source_refs FROM embeddings"
            )
        for row in cur.fetchall():
            rows.append(
                {
                    "doc_id": row[0],
                    "segment_id": row[1],
                    "start_ms": row[2],
                    "end_ms": row[3],
                    "speaker": row[4],
                    "text": row[5],
                    "embedding": _json_loads(row[6]),
                    "source_refs": _json_loads(row[7]) or {},
                }
            )
    return rows


def search_embeddings(
    query_embedding: List[float],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    rows = _load_embeddings()
    if not rows:
        return []
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for row in rows:
        emb = row.get("embedding")
        if not isinstance(emb, list):
            continue
        score = _cosine(query_embedding, emb)
        scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, row in scored[:limit]:
        results.append(
            {
                "doc_id": row.get("doc_id"),
                "segment_id": row.get("segment_id"),
                "start_ms": row.get("start_ms"),
                "end_ms": row.get("end_ms"),
                "speaker": row.get("speaker"),
                "text_snippet": row.get("text"),
                "score": score,
                "source_refs": row.get("source_refs") or {},
            }
        )
    return results
