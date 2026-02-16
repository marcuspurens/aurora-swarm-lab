"""Retrieve and rank evidence from embeddings, KB segments and memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.clients.ollama_client import embed
from app.clients.snowflake_client import SnowflakeClient
from app.core.config import load_settings
from app.modules.embeddings.embedding_store import search_embeddings
from app.modules.memory.context_handoff import load_handoff_text
from app.modules.memory.memory_recall import recall as recall_memory
from app.modules.memory.retrieval_feedback import apply_retrieval_feedback
from app.modules.memory.policy import overlap_score, tokens


def retrieve(
    query: str,
    limit: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    client: Optional[SnowflakeClient] = None,
) -> List[Dict[str, Any]]:
    settings = load_settings()
    filters = filters or {}
    query_tokens = tokens(query)
    candidates: List[Dict[str, Any]] = []
    fallback_sql = "N/A"

    if settings.embeddings_enabled:
        try:
            query_embedding = embed(query)
            embedded = search_embeddings(query_embedding, limit=max(limit * 2, limit))
            for row in embedded:
                item = {
                    "doc_id": row.get("doc_id"),
                    "segment_id": row.get("segment_id"),
                    "start_ms": row.get("start_ms"),
                    "end_ms": row.get("end_ms"),
                    "speaker": row.get("speaker"),
                    "text_snippet": row.get("text_snippet"),
                    "source_refs": row.get("source_refs") or {},
                    "score": _clamp_score(row.get("score"), default=0.0),
                    "retrieval_source": "embedding",
                }
                item["final_score"] = _score_candidate(item, query_tokens)
                candidates.append(item)
        except Exception:
            pass

    client = client or SnowflakeClient()
    sql = client.search_segments(query, limit=max(limit * 2, limit), filters=filters)
    fallback_sql = sql
    if hasattr(client, "execute_query"):
        try:
            rows = client.execute_query(sql)
        except Exception:
            rows = []
    else:
        rows = []

    for row in rows:
        text = row.get("text")
        lexical = overlap_score(query_tokens, text)
        item = {
            "doc_id": row.get("doc_id"),
            "segment_id": row.get("segment_id"),
            "start_ms": row.get("start_ms"),
            "end_ms": row.get("end_ms"),
            "speaker": row.get("speaker"),
            "text_snippet": text,
            "score": lexical,
            "retrieval_source": "keyword",
        }
        item["final_score"] = _score_candidate(item, query_tokens)
        candidates.append(item)

    if settings.context_handoff_enabled:
        try:
            handoff_text = load_handoff_text()
            if handoff_text:
                lexical = overlap_score(query_tokens, handoff_text)
                if lexical > 0.0 or _is_context_query(query):
                    item = {
                        "doc_id": "context:auto_handoff",
                        "segment_id": "state",
                        "start_ms": None,
                        "end_ms": None,
                        "speaker": "context",
                        "text_snippet": handoff_text[:1800],
                        "score": max(lexical, 0.15 if _is_context_query(query) else lexical),
                        "retrieval_source": "context",
                        "source_refs": {"kind": "auto_handoff"},
                    }
                    item["final_score"] = _score_candidate(item, query_tokens)
                    candidates.append(item)
        except Exception:
            pass

    if settings.memory_enabled:
        try:
            memory_type = filters.get("memory_type")
            memory_kind = filters.get("memory_kind")
            user_id = filters.get("user_id")
            project_id = filters.get("project_id")
            session_id = filters.get("session_id")
            memory_items = recall_memory(
                query=query,
                limit=max(1, min(settings.memory_retrieve_limit, limit)),
                memory_type=str(memory_type) if memory_type else None,
                memory_kind=str(memory_kind) if memory_kind else None,
                user_id=str(user_id) if user_id else None,
                project_id=str(project_id) if project_id else None,
                session_id=str(session_id) if session_id else None,
                include_long_term=True,
            )
            for item in memory_items:
                memory_id = str(item.get("memory_id") or "N/A")
                mem_score = _clamp_score(item.get("recall_score"), default=0.0)
                ev = {
                    "doc_id": f"memory:{memory_id}",
                    "segment_id": "memory",
                    "start_ms": None,
                    "end_ms": None,
                    "speaker": item.get("memory_type"),
                    "text_snippet": item.get("text"),
                    "score": mem_score,
                    "retrieval_source": "memory",
                    "source_refs": item.get("source_refs") or {},
                    "memory_type": item.get("memory_type"),
                    "memory_kind": item.get("memory_kind"),
                    "memory_id": memory_id,
                }
                ev["final_score"] = _score_candidate(ev, query_tokens)
                candidates.append(ev)
        except Exception:
            pass

    deduped = _dedupe_by_best_score(candidates)
    try:
        apply_retrieval_feedback(
            query,
            deduped,
            user_id=str(filters.get("user_id")) if filters.get("user_id") else None,
            project_id=str(filters.get("project_id")) if filters.get("project_id") else None,
            session_id=str(filters.get("session_id")) if filters.get("session_id") else None,
        )
    except Exception:
        pass
    deduped.sort(key=lambda row: float(row.get("final_score", 0.0)), reverse=True)
    top = deduped[:limit]
    if top:
        for row in top:
            row["score"] = float(row.get("final_score", row.get("score", 0.0)))
            row.pop("final_score", None)
        return top

    return [{"doc_id": "N/A", "segment_id": "N/A", "text_snippet": query, "sql": fallback_sql, "score": 0.0}]


def _score_candidate(row: Dict[str, Any], query_tokens: List[str]) -> float:
    source = str(row.get("retrieval_source") or "keyword")
    base_score = _clamp_score(row.get("score"), default=0.0)
    lexical = overlap_score(query_tokens, row.get("text_snippet"))
    source_bias = {"embedding": 0.28, "memory": 0.24, "keyword": 0.18, "context": 0.16}.get(source, 0.15)
    scored = source_bias + (0.52 * base_score) + (0.30 * lexical)
    return round(scored, 6)


def _dedupe_by_best_score(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        doc_id = str(row.get("doc_id") or "N/A")
        segment_id = str(row.get("segment_id") or "N/A")
        key = (doc_id, segment_id)
        current = by_key.get(key)
        if current is None or float(row.get("final_score", 0.0)) > float(current.get("final_score", 0.0)):
            by_key[key] = row
    return list(by_key.values())


def _clamp_score(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    if parsed < 0.0:
        return 0.0
    if parsed > 1.5:
        return 1.5
    return parsed


def _is_context_query(query: str) -> bool:
    lower = str(query or "").strip().lower()
    if not lower:
        return False
    hints = (
        "status",
        "continue",
        "context",
        "handoff",
        "next",
        "nasta",
        "roadmap",
        "focus",
        "working on",
        "what are we doing",
    )
    return any(h in lower for h in hints)
