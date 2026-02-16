"""Automatic context handoff helpers for long-running workstreams."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import load_settings
from app.modules.memory.policy import now_utc
from app.modules.memory.memory_write import write_memory
from app.queue.db import get_conn


HANDOFF_REL_PATH = "context/auto_handoff.md"
_QA_RE = re.compile(r"Q:\s*(.*?)\nA:\s*(.*)", re.DOTALL)
_ACTION_HINTS = ("next", "todo", "follow up", "action", "plan", "nasta", "fortsatt")
_DEFAULT_SESSION_KEY = "__default__"
_SESSION_LAST_SEEN: Dict[str, datetime] = {}
_SESSION_LOCK = threading.Lock()


def record_turn_and_refresh(
    question: str,
    answer_text: str,
    citations: Optional[List[Dict[str, object]]] = None,
) -> Dict[str, object]:
    q = _normalize_text(question, max_chars=1200)
    a = _normalize_text(answer_text, max_chars=3000)
    if q and a:
        write_memory(
            memory_type="session",
            text=f"Q: {q}\nA: {a}",
            topics=["context", "turn"],
            entities=[],
            source_refs={"kind": "context_turn", "citations": citations or []},
            importance=0.8,
            confidence=0.8,
            publish_long_term=False,
        )
        try:
            _maybe_precompact_session()
        except Exception:
            pass
    return refresh_handoff()


def refresh_handoff() -> Dict[str, object]:
    settings = load_settings()
    turn_limit = max(1, int(settings.context_handoff_turn_limit))
    turns = _load_recent_turns(turn_limit)
    text = _render_handoff(turns)
    path = handoff_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "text": text, "turn_count": len(turns), "updated_at": now_utc().isoformat()}


def load_handoff_text() -> Optional[str]:
    path = handoff_path()
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None
    return content if content.strip() else None


def get_handoff() -> Dict[str, object]:
    content = load_handoff_text()
    if content:
        return {"path": str(handoff_path()), "text": content, "exists": True}
    refreshed = refresh_handoff()
    return {"path": refreshed["path"], "text": refreshed["text"], "exists": False}


def handoff_path() -> Path:
    settings = load_settings()
    return settings.artifact_root / HANDOFF_REL_PATH


def inject_session_resume_evidence(
    evidence: List[Dict[str, object]],
    session_id: Optional[str] = None,
) -> bool:
    settings = load_settings()
    if not settings.context_handoff_enabled:
        return False
    if not _is_new_session_turn(session_id):
        return False
    handoff_text = load_handoff_text()
    if not handoff_text:
        return False

    for item in evidence:
        if str(item.get("doc_id") or "") == "context:auto_handoff":
            item["segment_id"] = str(item.get("segment_id") or "state")
            item["speaker"] = str(item.get("speaker") or "context")
            item["retrieval_source"] = str(item.get("retrieval_source") or "context")
            item["score"] = max(_safe_float(item.get("score"), default=0.0), 1.05)
            source_refs = item.get("source_refs")
            if not isinstance(source_refs, dict):
                source_refs = {}
            source_refs["kind"] = "auto_handoff"
            source_refs["injected"] = "session_resume"
            source_refs["session_id"] = _normalize_session_id(session_id)
            item["source_refs"] = source_refs
            return True

    evidence.insert(
        0,
        {
            "doc_id": "context:auto_handoff",
            "segment_id": "state",
            "start_ms": None,
            "end_ms": None,
            "speaker": "context",
            "text_snippet": handoff_text[:1800],
            "score": 1.05,
            "retrieval_source": "context",
            "source_refs": {
                "kind": "auto_handoff",
                "injected": "session_resume",
                "session_id": _normalize_session_id(session_id),
            },
        },
    )
    return True


def start_background_checkpoint() -> Optional[Dict[str, object]]:
    settings = load_settings()
    if not settings.context_handoff_enabled:
        return None
    interval_seconds = max(0, int(settings.context_handoff_background_interval_seconds))
    if interval_seconds <= 0:
        return None
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_background_checkpoint_loop,
        args=(stop_event, interval_seconds),
        name="aurora-context-handoff",
        daemon=True,
    )
    thread.start()
    return {"thread": thread, "stop_event": stop_event, "interval_seconds": interval_seconds}


def stop_background_checkpoint(handle: Optional[Dict[str, object]]) -> None:
    if not isinstance(handle, dict):
        return
    stop_event = handle.get("stop_event")
    thread = handle.get("thread")
    if isinstance(stop_event, threading.Event):
        stop_event.set()
    if isinstance(thread, threading.Thread):
        thread.join(timeout=1.0)


def reset_session_resume_tracking() -> None:
    with _SESSION_LOCK:
        _SESSION_LAST_SEEN.clear()


def _load_recent_turns(limit: int) -> List[Dict[str, object]]:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT text, source_refs, created_at FROM memory_items "
                "WHERE memory_type=? ORDER BY created_at DESC LIMIT ?",
                ("session", limit),
            )
        else:
            cur.execute(
                "SELECT text, source_refs, created_at FROM memory_items "
                "WHERE memory_type=%s ORDER BY created_at DESC LIMIT %s",
                ("session", limit),
            )
        rows = cur.fetchall()
    out: List[Dict[str, object]] = []
    for row in rows:
        text = str(row[0] or "")
        source_refs = _json_loads(row[1]) or {}
        created_at = str(row[2] or "")
        parsed = _parse_turn(text)
        if not parsed:
            continue
        out.append(
            {
                "question": parsed["question"],
                "answer": parsed["answer"],
                "citations": source_refs.get("citations", []) if isinstance(source_refs, dict) else [],
                "created_at": created_at,
            }
        )
    return out


def _count_session_turns() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute("SELECT COUNT(*) FROM memory_items WHERE memory_type=?", ("session",))
        else:
            cur.execute("SELECT COUNT(*) FROM memory_items WHERE memory_type=%s", ("session",))
        row = cur.fetchone()
    try:
        return int(row[0] if row else 0)
    except Exception:
        return 0


def _last_compacted_turn_count() -> int:
    like_pattern = '%"kind":"session_pre_compaction"%'
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT source_refs FROM memory_items WHERE source_refs LIKE ? "
                "ORDER BY created_at DESC LIMIT 20",
                (like_pattern,),
            )
        else:
            cur.execute(
                "SELECT source_refs FROM memory_items WHERE CAST(source_refs AS TEXT) ILIKE %s "
                "ORDER BY created_at DESC LIMIT 20",
                (like_pattern,),
            )
        rows = cur.fetchall()

    for row in rows:
        source_refs = _json_loads(row[0]) or {}
        if not isinstance(source_refs, dict):
            continue
        try:
            count = int(source_refs.get("turn_count") or 0)
        except Exception:
            count = 0
        if count > 0:
            return count
    return 0


def _maybe_precompact_session() -> Optional[Dict[str, object]]:
    settings = load_settings()
    threshold = max(0, int(settings.context_handoff_pre_compaction_turn_count))
    if threshold <= 0:
        return None

    turn_count = _count_session_turns()
    if turn_count < threshold or (turn_count % threshold) != 0:
        return None

    last_compacted = _last_compacted_turn_count()
    if last_compacted >= turn_count:
        return None

    turns = _load_recent_turns(limit=threshold)
    if not turns:
        return None

    summary = _render_pre_compaction_summary(turns, turn_count=turn_count)
    receipt = write_memory(
        memory_type="working",
        text=summary,
        topics=["context", "compaction"],
        entities=[],
        source_refs={
            "kind": "session_pre_compaction",
            "turn_count": turn_count,
            "threshold": threshold,
        },
        importance=0.75,
        confidence=0.7,
        publish_long_term=False,
        memory_kind="episodic",
    )
    return {"turn_count": turn_count, "memory_id": receipt.get("memory_id")}


def _render_pre_compaction_summary(turns: List[Dict[str, object]], turn_count: int) -> str:
    lines = [
        f"Session pre-compaction snapshot at {turn_count} turns.",
        "Latest focus:",
        f"- {str(turns[0].get('question') or '').strip()}",
        "Recent threads:",
    ]
    seen = set()
    for turn in turns[:6]:
        question = str(turn.get("question") or "").strip()
        if not question or question in seen:
            continue
        seen.add(question)
        lines.append(f"- {question}")
    latest_answer = str(turns[0].get("answer") or "").strip()
    if latest_answer:
        lines.extend(["Latest answer snapshot:", latest_answer[:420]])
    return "\n".join(lines).strip()


def _render_handoff(turns: List[Dict[str, object]]) -> str:
    now_iso = now_utc().isoformat()
    lines = ["# Aurora Auto Handoff", f"Updated: {now_iso}", ""]
    if not turns:
        lines.extend(
            [
                "Current focus:",
                "- No tracked turns yet.",
                "",
                "Next actions:",
                "- Start with an ask call and this handoff will auto-populate.",
                "",
            ]
        )
        return "\n".join(lines)

    latest = turns[0]
    lines.extend(["Current focus:", f"- {latest.get('question', '')}", ""])

    lines.append("Recent threads:")
    seen_q = set()
    for turn in turns[:6]:
        question = str(turn.get("question") or "").strip()
        if not question or question in seen_q:
            continue
        seen_q.add(question)
        lines.append(f"- {question}")
    lines.append("")

    latest_answer = str(latest.get("answer") or "").strip()
    if latest_answer:
        lines.extend(["Latest answer snapshot:", latest_answer[:800], ""])

    actions = _extract_actions(latest_answer)
    lines.append("Next actions:")
    if actions:
        for action in actions[:6]:
            lines.append(f"- {action}")
    else:
        lines.append("- Continue from latest focus and refine scope in the next ask.")
    lines.append("")

    citation_lines = _collect_citations(turns)
    if citation_lines:
        lines.append("Evidence anchors:")
        for citation in citation_lines:
            lines.append(f"- {citation}")
        lines.append("")

    return "\n".join(lines)


def _parse_turn(text: str) -> Optional[Dict[str, str]]:
    match = _QA_RE.search(text.strip())
    if not match:
        return None
    q = _normalize_text(match.group(1), max_chars=1200)
    a = _normalize_text(match.group(2), max_chars=3000)
    if not q:
        return None
    return {"question": q, "answer": a}


def _extract_actions(answer: str) -> List[str]:
    sentences = re.split(r"[.\n!?]+", answer or "")
    actions: List[str] = []
    for sentence in sentences:
        candidate = sentence.strip(" -\t")
        if not candidate:
            continue
        lower = candidate.lower()
        if any(hint in lower for hint in _ACTION_HINTS):
            actions.append(candidate[:180])
    if actions:
        return actions
    fallback = (answer or "").strip()
    if not fallback:
        return []
    return [fallback[:180]]


def _collect_citations(turns: List[Dict[str, object]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for turn in turns[:8]:
        citations = turn.get("citations")
        if not isinstance(citations, list):
            continue
        for item in citations:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("doc_id") or "").strip()
            segment_id = str(item.get("segment_id") or "").strip()
            if not doc_id:
                continue
            text = f"{doc_id}:{segment_id}" if segment_id else doc_id
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
            if len(out) >= 8:
                return out
    return out


def _normalize_text(text: object, max_chars: int) -> str:
    value = str(text or "").strip()
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip()


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


def _is_new_session_turn(session_id: Optional[str]) -> bool:
    settings = load_settings()
    now = now_utc()
    key = _normalize_session_id(session_id)
    idle_minutes = max(0, int(settings.context_handoff_resume_idle_minutes))
    with _SESSION_LOCK:
        last_seen = _SESSION_LAST_SEEN.get(key)
        _SESSION_LAST_SEEN[key] = now
    if last_seen is None:
        return True
    if idle_minutes <= 0:
        return False
    elapsed_seconds = (now - last_seen).total_seconds()
    return elapsed_seconds >= idle_minutes * 60


def _normalize_session_id(session_id: Optional[str]) -> str:
    value = str(session_id or "").strip()
    if not value:
        return _DEFAULT_SESSION_KEY
    if len(value) > 120:
        return value[:120]
    return value


def _background_checkpoint_loop(stop_event: threading.Event, interval_seconds: int) -> None:
    try:
        refresh_handoff()
    except Exception:
        pass
    while not stop_event.wait(interval_seconds):
        try:
            refresh_handoff()
        except Exception:
            pass


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default
