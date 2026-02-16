"""Retrospective retrieval feedback loop for memory-guided reranking."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import load_settings
from app.core.textnorm import normalize_user_text
from app.modules.memory.memory_write import write_memory
from app.modules.memory.policy import tokens
from app.queue.db import get_conn


def record_retrieval_feedback(
    question: str,
    evidence: List[Dict[str, object]],
    citations: List[Dict[str, object]],
    answer_text: str = "",
) -> Optional[Dict[str, object]]:
    settings = load_settings()
    if not settings.memory_enabled or not settings.retrieval_feedback_enabled:
        return None

    q = normalize_user_text(question, max_len=2400)
    if not q:
        return None

    ranked = list(evidence or [])[: max(1, min(10, int(settings.retrieval_feedback_signal_limit)))]
    if not ranked:
        return None

    cited_keys = {_citation_key(item) for item in (citations or [])}
    cited_keys.discard(None)

    signals: List[Dict[str, object]] = []
    for rank, row in enumerate(ranked, start=1):
        key = _evidence_key(row)
        if key is None:
            continue
        outcome = "cited" if key in cited_keys else "missed"
        signals.append(
            {
                "doc_id": key[0],
                "segment_id": key[1],
                "retrieval_source": str(row.get("retrieval_source") or ""),
                "outcome": outcome,
                "rank": rank,
            }
        )
    if not signals:
        return None

    cited_count = sum(1 for sig in signals if sig.get("outcome") == "cited")
    missed_count = len(signals) - cited_count
    ratio = (float(cited_count) / float(len(signals))) if signals else 0.0
    query_tokens = tokens(q)[:10]
    summary = (
        f"Retrieval feedback for question: {q[:240]}. "
        f"Cited={cited_count}, missed={missed_count}, evidence_considered={len(signals)}. "
        f"Answer snapshot: {normalize_user_text(answer_text, max_len=220)}"
    )
    receipt = write_memory(
        memory_type="working",
        text=summary,
        topics=["retrieval_feedback"] + query_tokens[:3],
        entities=[],
        source_refs={
            "kind": "retrieval_feedback",
            "query": q,
            "query_tokens": query_tokens,
            "signals": signals,
            "cited_count": cited_count,
            "missed_count": missed_count,
        },
        importance=0.58 + (0.22 * ratio),
        confidence=0.72,
        publish_long_term=False,
        memory_kind="procedural",
    )
    return {
        "memory_id": receipt.get("memory_id"),
        "signals": len(signals),
        "cited_count": cited_count,
        "missed_count": missed_count,
    }


def apply_retrieval_feedback(query: str, rows: List[Dict[str, Any]]) -> None:
    settings = load_settings()
    if not settings.memory_enabled or not settings.retrieval_feedback_enabled:
        return
    if not rows:
        return

    q_tokens = tokens(query)
    if not q_tokens:
        return

    feedback_items = _load_feedback_items(limit=max(1, int(settings.retrieval_feedback_history_limit)))
    if not feedback_items:
        return

    by_segment: Dict[Tuple[str, str], float] = {}
    by_doc: Dict[str, float] = {}
    min_overlap = max(0.0, float(settings.retrieval_feedback_min_token_overlap))
    for item in feedback_items:
        refs = item.get("source_refs") if isinstance(item.get("source_refs"), dict) else {}
        query_tokens = refs.get("query_tokens") if isinstance(refs, dict) else []
        if not isinstance(query_tokens, list):
            continue
        overlap = _token_overlap(q_tokens, [str(tok) for tok in query_tokens])
        if overlap < min_overlap:
            continue
        signals = refs.get("signals") if isinstance(refs, dict) else []
        if not isinstance(signals, list):
            continue
        for signal in signals:
            if not isinstance(signal, dict):
                continue
            doc_id = str(signal.get("doc_id") or "").strip()
            segment_id = str(signal.get("segment_id") or "").strip()
            if not doc_id:
                continue
            outcome = str(signal.get("outcome") or "").strip().lower()
            if outcome == "cited":
                delta = float(settings.retrieval_feedback_cited_boost) * overlap
            elif outcome == "missed":
                delta = -float(settings.retrieval_feedback_missed_penalty) * overlap
            else:
                continue
            if segment_id:
                key = (doc_id, segment_id)
                by_segment[key] = by_segment.get(key, 0.0) + delta
            by_doc[doc_id] = by_doc.get(doc_id, 0.0) + (0.5 * delta)

    if not by_segment and not by_doc:
        return

    for row in rows:
        doc_id = str(row.get("doc_id") or "").strip()
        segment_id = str(row.get("segment_id") or "").strip()
        if not doc_id:
            continue
        boost = by_doc.get(doc_id, 0.0) + by_segment.get((doc_id, segment_id), 0.0)
        if abs(boost) < 1e-9:
            continue
        base = _safe_float(row.get("final_score"), default=_safe_float(row.get("score"), default=0.0))
        row["feedback_boost"] = round(boost, 6)
        row["final_score"] = round(max(0.0, base + boost), 6)


def _load_feedback_items(limit: int) -> List[Dict[str, object]]:
    like_pattern = '%"kind"%retrieval_feedback%'
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT source_refs, created_at FROM memory_items "
                "WHERE memory_type=? AND source_refs LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                ("working", like_pattern, limit),
            )
        else:
            cur.execute(
                "SELECT source_refs, created_at FROM memory_items "
                "WHERE memory_type=%s AND CAST(source_refs AS TEXT) ILIKE %s "
                "ORDER BY created_at DESC LIMIT %s",
                ("working", like_pattern, limit),
            )
        rows = cur.fetchall()

    out: List[Dict[str, object]] = []
    for row in rows:
        refs = _json_loads(row[0]) or {}
        if not isinstance(refs, dict):
            continue
        if str(refs.get("kind") or "") != "retrieval_feedback":
            continue
        out.append({"source_refs": refs, "created_at": row[1]})
    return out


def _evidence_key(row: Dict[str, object]) -> Optional[Tuple[str, str]]:
    doc_id = str(row.get("doc_id") or "").strip()
    segment_id = str(row.get("segment_id") or "").strip()
    if not doc_id:
        return None
    return doc_id, segment_id


def _citation_key(row: Dict[str, object]) -> Optional[Tuple[str, str]]:
    doc_id = str(row.get("doc_id") or "").strip()
    segment_id = str(row.get("segment_id") or "").strip()
    if not doc_id:
        return None
    return doc_id, segment_id


def _token_overlap(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    a_set = set(str(x).lower() for x in a if x)
    b_set = set(str(x).lower() for x in b if x)
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / float(len(a_set))


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


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
