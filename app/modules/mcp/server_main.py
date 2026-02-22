"""Minimal MCP-style JSON-RPC server over stdio."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from app.core.config import load_settings
from app.core.ids import make_source_id, sha256_file
from app.core.logging import configure_logging
from app.core.textnorm import normalize_identifier, normalize_user_text
from app.modules.graph.graph_retrieve import retrieve as graph_retrieve
from app.modules.retrieve.retrieve_snowflake import retrieve
from app.modules.swarm.analyze import analyze
from app.modules.swarm.route import route_question
from app.modules.swarm.synthesize import synthesize
from app.modules.intake.intake_url import compute_source_version as compute_url_version
from app.modules.intake.intake_youtube import compute_source_version as compute_youtube_version
from app.clients.youtube_client import get_video_info
from app.queue.jobs import enqueue_job
from app.queue.db import init_db, get_conn
from app.modules.memory.memory_write import write_memory
from app.modules.memory.memory_recall import recall as recall_memory
from app.modules.memory.memory_stats import get_memory_stats
from app.modules.memory.maintenance import run_memory_maintenance
from app.modules.memory.router import parse_explicit_remember, route_memory
from app.modules.memory.retrieval_feedback import record_retrieval_feedback
from app.modules.memory.context_handoff import (
    get_handoff,
    inject_session_resume_evidence,
    record_turn_and_refresh,
    start_background_checkpoint,
    stop_background_checkpoint,
)
from app.modules.voiceprint.gallery import list_voiceprints, upsert_person
from app.modules.intake.ingest_auto import extract_items, enqueue_items
from app.modules.intake.intake_obsidian import enqueue as enqueue_obsidian_note
from app.modules.intake.intake_image import enqueue as enqueue_image
from app.modules.security.ingest_allowlist import ensure_ingest_path_allowed


TOOLS = [
    {
        "name": "ingest_url",
        "description": "Enqueue URL for ingest",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "ingest_doc",
        "description": "Enqueue document for ingest",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "ingest_image",
        "description": "Enqueue image file for OCR text extraction",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "ingest_youtube",
        "description": "Enqueue YouTube URL for ingest",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "ask",
        "description": "Ask question via swarm pipeline",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 2400},
                "remember": {"type": "boolean"},
                "intent": {"type": "string", "minLength": 1, "maxLength": 40},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "memory_write",
        "description": "Write memory item",
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "text": {"type": "string"},
                "topics": {"type": "array"},
                "entities": {"type": "array"},
                "source_refs": {"type": "object"},
                "importance": {"type": "number"},
                "confidence": {"type": "number"},
                "expires_at": {"type": "string"},
                "pinned_until": {"type": "string"},
                "publish_long_term": {"type": "boolean"},
                "intent": {"type": "string", "minLength": 1, "maxLength": 40},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["type", "text"],
        },
    },
    {
        "name": "memory_recall",
        "description": "Recall memory items",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "type": {"type": "string"},
                "include_long_term": {"type": "boolean"},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_stats",
        "description": "Memory observability stats",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
        },
    },
    {
        "name": "memory_maintain",
        "description": "Run or enqueue memory lifecycle maintenance",
        "input_schema": {
            "type": "object",
            "properties": {
                "enqueue": {"type": "boolean"},
                "user_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "project_id": {"type": "string", "minLength": 1, "maxLength": 120},
                "session_id": {"type": "string", "minLength": 1, "maxLength": 120},
            },
        },
    },
    {
        "name": "context_handoff",
        "description": "Get the latest automatic context handoff snapshot",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "status",
        "description": "Queue job status counts",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "dashboard_stats",
        "description": "Dashboard counters and progress for docs, vectorization, memory, and queue",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_docs": {"type": "integer"},
                "target_vectors": {"type": "integer"},
                "target_memory": {"type": "integer"},
            },
        },
    },
    {
        "name": "dashboard_timeseries",
        "description": "Timeseries buckets for pipeline activity (docs, vectors, memory, jobs)",
        "input_schema": {
            "type": "object",
            "properties": {
                "window_hours": {"type": "integer"},
                "bucket_minutes": {"type": "integer"},
            },
        },
    },
    {
        "name": "dashboard_alerts",
        "description": "Operational alerts for queue, failures, and recent errors",
        "input_schema": {
            "type": "object",
            "properties": {
                "stale_running_minutes": {"type": "integer"},
                "error_window_hours": {"type": "integer"},
            },
        },
    },
    {
        "name": "dashboard_models",
        "description": "Model/tokens observability metrics (local estimates from run logs)",
        "input_schema": {
            "type": "object",
            "properties": {
                "window_hours": {"type": "integer"},
            },
        },
    },
    {
        "name": "voice_gallery_list",
        "description": "List voiceprints for voice gallery",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "voice_gallery_update",
        "description": "Update voice gallery entry with EBUCore+ fields",
        "input_schema": {
            "type": "object",
            "properties": {
                "voiceprint_id": {"type": "string"},
                "given_name": {"type": "string"},
                "family_name": {"type": "string"},
                "title": {"type": "string"},
                "role": {"type": "string"},
                "affiliation": {"type": "string"},
                "aliases": {"type": "array"},
                "tags": {"type": "array"},
                "notes": {"type": "string"},
                "person_id": {"type": "string"},
            },
            "required": ["voiceprint_id"],
        },
    },
    {
        "name": "voice_gallery_open",
        "description": "Open voice gallery UI",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "ingest_auto",
        "description": "Enqueue links for ingest (auto-detect YouTube, URL, or local file paths)",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "items": {"type": "array"},
                "dedupe": {"type": "boolean"},
                "tags": {"type": "array"},
                "context": {"type": "string"},
                "speaker": {"type": "string"},
                "organization": {"type": "string"},
                "event_date": {"type": "string"},
                "source_metadata": {"type": "object"},
            },
        },
    },
    {
        "name": "intake_open",
        "description": "Open intake UI for paste-and-ingest",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "obsidian_watch_status",
        "description": "Show Obsidian vault configuration and watcher command",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "obsidian_list_notes",
        "description": "List markdown notes in configured Obsidian vault",
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string"},
                "limit": {"type": "integer"},
                "include_outputs": {"type": "boolean"},
            },
        },
    },
    {
        "name": "obsidian_enqueue_note",
        "description": "Parse Obsidian note frontmatter/auto rules and enqueue Aurora jobs",
        "input_schema": {
            "type": "object",
            "properties": {"note_path": {"type": "string"}},
            "required": ["note_path"],
        },
    },
    {
        "name": "dashboard_open",
        "description": "Open dashboard UI",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_INTENT_ALIASES = {
    "write": {"write", "memory_write", "save", "store"},
    "remember": {"remember", "memory_remember", "kom_ihag"},
    "todo": {"todo", "task", "memory_todo"},
}


def _normalize_policy_token(value: object, max_len: int = 120) -> str:
    token = normalize_identifier(value, max_len=max_len).lower()
    token = re.sub(r"[\s\-]+", "_", token)
    return token.strip("_")


def _normalize_tool_name(value: object) -> str:
    return _normalize_policy_token(value, max_len=80)


def _parse_tool_set(raw: object) -> Optional[set[str]]:
    text = str(raw or "").strip()
    if not text:
        return None
    items = set()
    for token in re.split(r"[,\s]+", text):
        name = _normalize_tool_name(token)
        if not name:
            continue
        if name in {"*", "all"}:
            return None
        if name in {"none", "deny_all"}:
            return set()
        items.add(name)
    if not items:
        return set()
    return items


def _parse_tool_allowlist_by_client(raw: object) -> Dict[str, Optional[set[str]]]:
    text = str(raw or "").strip()
    if not text:
        return {}
    out: Dict[str, Optional[set[str]]] = {}
    for chunk in re.split(r"[;\n]+", text):
        entry = chunk.strip()
        if not entry or "=" not in entry:
            continue
        key_raw, value_raw = entry.split("=", 1)
        key = _normalize_policy_token(key_raw, max_len=120)
        if not key:
            continue
        out[key] = _parse_tool_set(value_raw)
    return out


def _intersect_allowlists(first: Optional[set[str]], second: Optional[set[str]]) -> Optional[set[str]]:
    if first is None and second is None:
        return None
    if first is None:
        return second
    if second is None:
        return first
    return first.intersection(second)


def _resolve_request_tags(req: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
    client_id = _normalize_policy_token(params.get("client_id") or req.get("client_id"), max_len=120)
    use_case = _normalize_policy_token(params.get("use_case") or req.get("use_case"), max_len=120)
    out: Dict[str, str] = {}
    if client_id:
        out["client_id"] = client_id
    if use_case:
        out["use_case"] = use_case
    return out


def _resolve_tool_allowlist(req: Dict[str, Any], params: Dict[str, Any]) -> Optional[set[str]]:
    settings = load_settings()
    global_allow = _parse_tool_set(settings.mcp_tool_allowlist)
    by_client = _parse_tool_allowlist_by_client(settings.mcp_tool_allowlist_by_client)
    tags = _resolve_request_tags(req, params)
    client_id = tags.get("client_id")
    use_case = tags.get("use_case")

    specific: Optional[set[str]] = None
    keys: List[str] = []
    if client_id and use_case:
        keys.append(f"{client_id}/{use_case}")
    if client_id:
        keys.append(client_id)
    if use_case:
        keys.append(f"@{use_case}")

    for key in keys:
        if key in by_client:
            specific = by_client[key]
            break

    return _intersect_allowlists(global_allow, specific)


def _require_tool_allowed(tool_name: str, req: Dict[str, Any], params: Dict[str, Any]) -> None:
    allowlist = _resolve_tool_allowlist(req, params)
    if allowlist is None:
        return
    if _normalize_tool_name(tool_name) in allowlist:
        return
    tags = _resolve_request_tags(req, params)
    context = ""
    if tags:
        context = " " + ", ".join(f"{k}={v}" for k, v in tags.items())
    raise PermissionError(f"Tool '{tool_name}' is not allowed by MCP tool allowlist.{context}")


def _filter_tools_for_request(req: Dict[str, Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    allowlist = _resolve_tool_allowlist(req, params)
    if allowlist is None:
        return TOOLS
    return [tool for tool in TOOLS if _normalize_tool_name(tool.get("name")) in allowlist]


def _normalize_intent(value: object) -> str:
    return _normalize_policy_token(value, max_len=40)


def _require_action_intent(args: Dict[str, Any], action: str, error_prefix: str) -> str:
    settings = load_settings()
    if not settings.mcp_require_explicit_intent:
        return ""
    required = _normalize_policy_token(action, max_len=40)
    provided = _normalize_intent(args.get("intent"))
    if not provided:
        raise ValueError(f"{error_prefix}.intent is required for action '{required}'")
    allowed = _INTENT_ALIASES.get(required, {required})
    if provided not in allowed:
        allowed_hint = ", ".join(sorted(allowed))
        raise ValueError(f"{error_prefix}.intent='{provided}' does not match action '{required}' (allowed: {allowed_hint})")
    return provided


def _is_todo_memory_write(args: Dict[str, Any]) -> bool:
    text = normalize_user_text(args.get("text"), max_len=280).lower()
    if text.startswith("todo:"):
        return True
    topics = args.get("topics")
    if isinstance(topics, list):
        for topic in topics:
            if _normalize_policy_token(topic, max_len=40) == "todo":
                return True
    source_refs = args.get("source_refs")
    if isinstance(source_refs, dict):
        kind = _normalize_policy_token(source_refs.get("kind"), max_len=80)
        if "todo" in kind:
            return True
    return False


def _status() -> Dict[str, int]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        rows = cur.fetchall()
    return {row[0]: int(row[1]) for row in rows}


def _dashboard_target(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(str(raw or "").strip())
    except Exception:
        value = default
    return max(1, value)


def _to_int(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _pct(value: int, target: int) -> float:
    if target <= 0:
        return 0.0
    pct = (float(value) / float(target)) * 100.0
    if pct < 0.0:
        return 0.0
    if pct > 100.0:
        return 100.0
    return round(pct, 1)


def _tool_dashboard_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    target_docs = max(1, _to_int(args.get("target_docs") or _dashboard_target("AURORA_DASHBOARD_TARGET_DOCS", 50)))
    target_vectors = max(
        1, _to_int(args.get("target_vectors") or _dashboard_target("AURORA_DASHBOARD_TARGET_VECTORS", 2500))
    )
    target_memory = max(
        1, _to_int(args.get("target_memory") or _dashboard_target("AURORA_DASHBOARD_TARGET_MEMORY", 400))
    )
    docs_total = 0
    vectors_total = 0
    vectors_docs = 0
    memory_total = 0
    memory_by_type: Dict[str, int] = {}

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM manifests")
        row = cur.fetchone()
        docs_total = _to_int(row[0] if row else 0)

        cur.execute("SELECT COUNT(*) FROM embeddings")
        row = cur.fetchone()
        vectors_total = _to_int(row[0] if row else 0)

        if conn.is_sqlite:
            cur.execute("SELECT COUNT(DISTINCT source_id || '|' || source_version) FROM embeddings")
        else:
            cur.execute("SELECT COUNT(DISTINCT CONCAT(source_id, '|', source_version)) FROM embeddings")
        row = cur.fetchone()
        vectors_docs = _to_int(row[0] if row else 0)

        cur.execute("SELECT COUNT(*) FROM memory_items")
        row = cur.fetchone()
        memory_total = _to_int(row[0] if row else 0)

        cur.execute("SELECT memory_type, COUNT(*) FROM memory_items GROUP BY memory_type")
        rows = cur.fetchall()
        for type_row in rows:
            key = str(type_row[0] or "unknown")
            memory_by_type[key] = _to_int(type_row[1])

    jobs = _status()
    return {
        "targets": {
            "docs": target_docs,
            "vectors": target_vectors,
            "memory": target_memory,
        },
        "counts": {
            "docs_total": docs_total,
            "vectors_total": vectors_total,
            "vectors_docs": vectors_docs,
            "memory_total": memory_total,
            "memory_by_type": memory_by_type,
        },
        "progress": {
            "docs_percent": _pct(docs_total, target_docs),
            "vectors_percent": _pct(vectors_total, target_vectors),
            "memory_percent": _pct(memory_total, target_memory),
        },
        "queue": jobs,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json_object(value: object) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    raw = value.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _parse_datetime(value: object) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _to_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _estimate_tokens(chars: int) -> int:
    return max(0, int((max(0, int(chars)) + 3) // 4))


def _tool_dashboard_timeseries(args: Dict[str, Any]) -> Dict[str, Any]:
    window_hours = max(1, min(24 * 14, _to_int(args.get("window_hours") or 24)))
    bucket_minutes = max(5, min(12 * 60, _to_int(args.get("bucket_minutes") or 60)))
    bucket_seconds = bucket_minutes * 60
    end = _utc_now()
    start = end - timedelta(hours=window_hours)
    aligned_start = datetime.fromtimestamp((int(start.timestamp()) // bucket_seconds) * bucket_seconds, tz=timezone.utc)
    bucket_count = max(1, int(((end - aligned_start).total_seconds() // bucket_seconds) + 1))
    buckets: List[Dict[str, Any]] = []

    for index in range(bucket_count):
        bucket_start = aligned_start + timedelta(seconds=index * bucket_seconds)
        bucket_end = bucket_start + timedelta(seconds=bucket_seconds)
        label = bucket_start.strftime("%m-%d %H:%M")
        buckets.append(
            {
                "start": bucket_start.isoformat(),
                "end": bucket_end.isoformat(),
                "label": label,
                "docs_ingested": 0,
                "vectors_built": 0,
                "memory_written": 0,
                "jobs_done": 0,
                "jobs_failed": 0,
                "jobs_enqueued": 0,
            }
        )

    def add_event(ts: Optional[datetime], key: str, amount: int = 1) -> None:
        if ts is None:
            return
        if ts < aligned_start or ts > end:
            return
        idx = int((ts - aligned_start).total_seconds() // bucket_seconds)
        if idx < 0 or idx >= len(buckets):
            return
        buckets[idx][key] = _to_int(buckets[idx].get(key)) + max(0, amount)

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT updated_at FROM manifests")
        for row in cur.fetchall():
            add_event(_parse_datetime(row[0] if row else None), "docs_ingested", 1)

        cur.execute("SELECT updated_at FROM embeddings")
        for row in cur.fetchall():
            add_event(_parse_datetime(row[0] if row else None), "vectors_built", 1)

        cur.execute("SELECT created_at FROM memory_items")
        for row in cur.fetchall():
            add_event(_parse_datetime(row[0] if row else None), "memory_written", 1)

        cur.execute("SELECT status, created_at, updated_at FROM jobs")
        for row in cur.fetchall():
            status = str(row[0] or "")
            add_event(_parse_datetime(row[1]), "jobs_enqueued", 1)
            if status == "done":
                add_event(_parse_datetime(row[2]), "jobs_done", 1)
            elif status == "failed":
                add_event(_parse_datetime(row[2]), "jobs_failed", 1)

    totals = {
        "docs_ingested": sum(_to_int(b.get("docs_ingested")) for b in buckets),
        "vectors_built": sum(_to_int(b.get("vectors_built")) for b in buckets),
        "memory_written": sum(_to_int(b.get("memory_written")) for b in buckets),
        "jobs_done": sum(_to_int(b.get("jobs_done")) for b in buckets),
        "jobs_failed": sum(_to_int(b.get("jobs_failed")) for b in buckets),
        "jobs_enqueued": sum(_to_int(b.get("jobs_enqueued")) for b in buckets),
    }
    return {
        "window_hours": window_hours,
        "bucket_minutes": bucket_minutes,
        "start": aligned_start.isoformat(),
        "end": end.isoformat(),
        "totals": totals,
        "buckets": buckets,
    }


def _tool_dashboard_alerts(args: Dict[str, Any]) -> Dict[str, Any]:
    stale_running_minutes = max(1, min(24 * 60, _to_int(args.get("stale_running_minutes") or 20)))
    error_window_hours = max(1, min(24 * 14, _to_int(args.get("error_window_hours") or 24)))
    stale_before = _utc_now() - timedelta(minutes=stale_running_minutes)
    error_since = _utc_now() - timedelta(hours=error_window_hours)

    queue_counts = _status()
    running_stale = 0
    queued_retries = 0
    recent_errors = 0

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT status, attempts, updated_at FROM jobs")
        for row in cur.fetchall():
            status = str(row[0] or "")
            attempts = _to_int(row[1])
            updated_at = _parse_datetime(row[2])
            if status == "running" and updated_at and updated_at < stale_before:
                running_stale += 1
            if status == "queued" and attempts > 0:
                queued_retries += 1

        cur.execute("SELECT created_at, error FROM run_log WHERE error IS NOT NULL")
        for row in cur.fetchall():
            created_at = _parse_datetime(row[0])
            if created_at and created_at >= error_since and str(row[1] or "").strip():
                recent_errors += 1

    alerts: List[Dict[str, Any]] = []
    if running_stale > 0:
        alerts.append(
            {
                "severity": "critical",
                "code": "running_jobs_stale",
                "title": "Stale running jobs",
                "detail": f"{running_stale} job(s) marked running for more than {stale_running_minutes} minute(s).",
            }
        )
    failed_total = _to_int(queue_counts.get("failed"))
    if failed_total > 0:
        alerts.append(
            {
                "severity": "high",
                "code": "queue_failed_jobs",
                "title": "Failed jobs in queue",
                "detail": f"{failed_total} failed job(s) require attention.",
            }
        )
    queued_total = _to_int(queue_counts.get("queued"))
    if queued_total >= 50:
        alerts.append(
            {
                "severity": "medium",
                "code": "queue_backlog",
                "title": "Queue backlog growing",
                "detail": f"{queued_total} queued job(s) currently waiting.",
            }
        )
    if queued_retries > 0:
        alerts.append(
            {
                "severity": "medium",
                "code": "retry_backoff",
                "title": "Jobs retrying with backoff",
                "detail": f"{queued_retries} queued job(s) are on retry attempts.",
            }
        )
    if recent_errors >= 20:
        alerts.append(
            {
                "severity": "medium",
                "code": "recent_errors",
                "title": "High recent error volume",
                "detail": f"{recent_errors} run errors in last {error_window_hours}h.",
            }
        )
    if not alerts:
        alerts.append(
            {
                "severity": "ok",
                "code": "all_clear",
                "title": "No active alerts",
                "detail": "Queue and run logs look healthy for current thresholds.",
            }
        )

    return {
        "summary": {
            "queue": queue_counts,
            "running_stale": running_stale,
            "queued_retries": queued_retries,
            "recent_errors": recent_errors,
            "stale_running_minutes": stale_running_minutes,
            "error_window_hours": error_window_hours,
        },
        "alerts": alerts,
        "updated_at": _utc_now().isoformat(),
    }


def _tool_dashboard_models(args: Dict[str, Any]) -> Dict[str, Any]:
    window_hours = max(1, min(24 * 14, _to_int(args.get("window_hours") or 24)))
    since = _utc_now() - timedelta(hours=window_hours)
    per_model: Dict[str, Dict[str, Any]] = {}

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT created_at, component, model, input_json, output_json, error FROM run_log")
        for row in cur.fetchall():
            created_at = _parse_datetime(row[0])
            if not created_at or created_at < since:
                continue
            component = str(row[1] or "")
            model = str(row[2] or "").strip()
            if not model:
                continue

            input_payload = _parse_json_object(row[3])
            output_payload = _parse_json_object(row[4])
            error_text = str(row[5] or "").strip()

            model_key = model
            model_stats = per_model.setdefault(
                model_key,
                {
                    "model": model_key,
                    "requests": 0,
                    "errors": 0,
                    "components": {},
                    "prompt_chars": 0,
                    "completion_chars": 0,
                },
            )
            model_stats["requests"] = _to_int(model_stats.get("requests")) + 1
            if error_text:
                model_stats["errors"] = _to_int(model_stats.get("errors")) + 1

            comp_counts = model_stats.get("components")
            if isinstance(comp_counts, dict):
                comp_counts[component] = _to_int(comp_counts.get(component)) + 1

            prompt_chars = _to_int(input_payload.get("egress_policy_input_chars"))
            if prompt_chars <= 0:
                prompt_chars = (
                    _to_int(input_payload.get("question_len"))
                    + _to_int(input_payload.get("evidence_prompt_chars"))
                    + _to_int(input_payload.get("analysis_prompt_chars"))
                )
            completion_chars = 0
            answer_text = output_payload.get("answer_text")
            if isinstance(answer_text, str):
                completion_chars += len(answer_text)
            claims = output_payload.get("claims")
            if isinstance(claims, list):
                completion_chars += sum(len(str(x or "")) for x in claims)
            timeline = output_payload.get("timeline")
            if isinstance(timeline, list):
                completion_chars += sum(len(str(x or "")) for x in timeline)
            open_questions = output_payload.get("open_questions")
            if isinstance(open_questions, list):
                completion_chars += sum(len(str(x or "")) for x in open_questions)

            model_stats["prompt_chars"] = _to_int(model_stats.get("prompt_chars")) + prompt_chars
            model_stats["completion_chars"] = _to_int(model_stats.get("completion_chars")) + completion_chars

    models: List[Dict[str, Any]] = []
    total_requests = 0
    total_errors = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for stats in per_model.values():
        requests = _to_int(stats.get("requests"))
        errors = _to_int(stats.get("errors"))
        prompt_tokens = _estimate_tokens(_to_int(stats.get("prompt_chars")))
        completion_tokens = _estimate_tokens(_to_int(stats.get("completion_chars")))
        total_requests += requests
        total_errors += errors
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        models.append(
            {
                "model": str(stats.get("model") or "unknown"),
                "requests": requests,
                "errors": errors,
                "error_rate_pct": round((errors / requests) * 100.0, 2) if requests > 0 else 0.0,
                "prompt_tokens_est": prompt_tokens,
                "completion_tokens_est": completion_tokens,
                "components": stats.get("components") or {},
            }
        )

    models.sort(key=lambda item: (_to_int(item.get("requests")), str(item.get("model"))), reverse=True)
    return {
        "window_hours": window_hours,
        "summary": {
            "requests": total_requests,
            "errors": total_errors,
            "error_rate_pct": round((total_errors / total_requests) * 100.0, 2) if total_requests > 0 else 0.0,
            "prompt_tokens_est": total_prompt_tokens,
            "completion_tokens_est": total_completion_tokens,
        },
        "models": models,
        "codex_usage": {
            "available": False,
            "reason": "Codex Desktop/API token usage is not exposed in Aurora local run_log.",
        },
        "updated_at": _utc_now().isoformat(),
    }


def _mcp_capabilities() -> Dict[str, Any]:
    return {
        "tools": {"listChanged": False},
        "resources": {"subscribe": False, "listChanged": False},
    }


def _mcp_server_info() -> Dict[str, str]:
    return {"name": "aurora-swarm-lab", "version": "0.1.0"}


def _resource_catalog() -> List[Dict[str, str]]:
    return [
        {
            "uri": "ui://voice-gallery",
            "name": "Aurora Voice Gallery UI",
            "mime_type": "text/html",
            "mimeType": "text/html",
        },
        {
            "uri": "ui://intake",
            "name": "Aurora Intake UI",
            "mime_type": "text/html",
            "mimeType": "text/html",
        },
        {
            "uri": "ui://dashboard",
            "name": "Aurora Dashboard UI",
            "mime_type": "text/html",
            "mimeType": "text/html",
        },
    ]


def _read_resource(uri: str) -> Tuple[str, str]:
    if uri == "ui://voice-gallery":
        return "text/html", _voice_gallery_html()
    if uri == "ui://intake":
        return "text/html", _intake_html()
    if uri == "ui://dashboard":
        return "text/html", _dashboard_html()
    raise ValueError(f"Unknown resource: {uri}")


def _tool_for_mcp(tool: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(tool)
    schema = out.get("input_schema")
    if isinstance(schema, dict):
        out.setdefault("inputSchema", schema)
    return out


def _tool_ingest_url(args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(args["url"])
    source_id = make_source_id("url", url)
    source_version = compute_url_version(url)
    job_id = enqueue_job("ingest_url", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}


def _tool_ingest_doc(args: Dict[str, Any]) -> Dict[str, Any]:
    path = ensure_ingest_path_allowed(Path(str(args["path"])), source="mcp.ingest_doc")
    source_id = make_source_id("file", str(path))
    source_version = sha256_file(path)
    job_id = enqueue_job("ingest_doc", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}



def _tool_ingest_image(args: Dict[str, Any]) -> Dict[str, Any]:
    path = str(args.get("path", ""))
    resolved = str(ensure_ingest_path_allowed(Path(path), source="mcp.ingest_image"))
    source_id = make_source_id("image", resolved)
    source_version = sha256_file(Path(resolved))
    job_id = enqueue_job("ingest_image", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}

def _tool_ingest_youtube(args: Dict[str, Any]) -> Dict[str, Any]:
    url = str(args["url"])
    info = get_video_info(url)
    video_id = str(info.get("id") or "unknown")
    source_id = make_source_id("youtube", video_id)
    source_version = compute_youtube_version(url)
    job_id = enqueue_job("ingest_youtube", "io", source_id, source_version)
    return {"job_id": job_id, "source_id": source_id, "source_version": source_version}


def _tool_ask(args: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"question", "remember", "intent", "user_id", "project_id", "session_id"}
    unknown = sorted(str(k) for k in args.keys() if k not in allowed)
    if unknown:
        raise ValueError(f"ask received unknown argument(s): {', '.join(unknown)}")

    question_raw = args.get("question")
    if not isinstance(question_raw, str):
        raise ValueError("ask.question must be a string")
    question = normalize_user_text(question_raw, max_len=2400)
    if not question:
        raise ValueError("ask.question must be a non-empty string")
    remember = _parse_bool(args.get("remember", False))
    scope = _parse_scope_arguments(args, error_prefix="ask")
    session_id = scope.get("session_id")
    provided_intent = _normalize_intent(args.get("intent"))
    remember_directive = parse_explicit_remember(question)
    if remember_directive and remember_directive.get("text"):
        guard_intent = _require_action_intent(args, action="remember", error_prefix="ask")
        receipt = _write_routed_ask_memory(
            memory_text=str(remember_directive.get("text") or ""),
            question=question,
            trigger="explicit_remember",
            preferred_kind=remember_directive.get("memory_kind"),
            intent=guard_intent or provided_intent,
            user_id=scope.get("user_id"),
            project_id=scope.get("project_id"),
            session_id=session_id,
        )
        kind = str(receipt.get("memory_kind") or "semantic")
        superseded = int(receipt.get("superseded_count") or 0)
        extra = f" superseded={superseded}" if superseded > 0 else ""
        return {"answer_text": f"Saved memory [{kind}] id={receipt['memory_id']}.{extra}".strip(), "citations": []}

    plan = route_question(question)
    plan_filters = dict(plan.filters or {})
    plan_filters.update(scope)
    evidence = retrieve(question, limit=plan.retrieve_top_k, filters=plan_filters)
    graph_evidence = []
    try:
        graph_evidence = graph_retrieve(question, limit=plan.retrieve_top_k, hops=1)
    except Exception:
        graph_evidence = []
    combined = evidence + (graph_evidence or [])
    try:
        inject_session_resume_evidence(combined, session_id=str(session_id) if session_id else None)
    except Exception:
        pass
    need_strong = plan.need_strong_model or len(combined) < 2
    analysis = analyze(question, combined) if need_strong else None
    result = synthesize(question, combined, analysis=analysis, use_strong_model=need_strong)
    payload = result.model_dump()
    try:
        record_retrieval_feedback(
            question=question,
            evidence=combined,
            citations=payload.get("citations") or [],
            answer_text=str(payload.get("answer_text") or ""),
            user_id=scope.get("user_id"),
            project_id=scope.get("project_id"),
            session_id=session_id,
        )
    except Exception:
        pass
    try:
        record_turn_and_refresh(
            question=question,
            answer_text=str(payload.get("answer_text") or ""),
            citations=payload.get("citations") or [],
        )
    except Exception:
        pass
    if remember:
        guard_intent = _require_action_intent(args, action="remember", error_prefix="ask")
        _write_routed_ask_memory(
            memory_text=f"Q: {question}\nA: {payload.get('answer_text','')}",
            question=question,
            trigger="remember_flag",
            intent=guard_intent or provided_intent,
            user_id=scope.get("user_id"),
            project_id=scope.get("project_id"),
            session_id=session_id,
        )
    return payload


def _write_routed_ask_memory(
    memory_text: str,
    question: str,
    trigger: str,
    preferred_kind: Optional[str] = None,
    intent: Optional[str] = None,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    route = route_memory(memory_text, preferred_kind=preferred_kind)
    importance = 0.8 if str(route.get("memory_kind")) != "episodic" else 0.68
    source_refs = {"kind": "ask_memory", "trigger": trigger, "question": question}
    if intent:
        source_refs["intent_action"] = "remember"
        source_refs["intent_provided"] = intent
        source_refs["intent_guard"] = "mcp_explicit_intent"
    return write_memory(
        memory_type=str(route.get("memory_type") or "working"),
        text=memory_text,
        topics=["ask", "remember"],
        entities=[],
        source_refs=source_refs,
        importance=importance,
        confidence=float(route.get("confidence") or 0.7),
        publish_long_term=False,
        memory_kind=str(route.get("memory_kind") or "semantic"),
        memory_slot=str(route.get("memory_slot") or "") or None,
        memory_value=str(route.get("memory_value") or "") or None,
        overwrite_conflicts=True,
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
    )


def _tool_memory_write(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = _parse_scope_arguments(args, error_prefix="memory_write")
    action = "todo" if _is_todo_memory_write(args) else "write"
    intent = _require_action_intent(args, action=action, error_prefix="memory_write")
    source_refs = dict(args.get("source_refs") or {})
    if intent:
        source_refs.setdefault("intent_action", action)
        source_refs.setdefault("intent_provided", intent)
        source_refs.setdefault("intent_guard", "mcp_explicit_intent")
    return write_memory(
        memory_type=str(args["type"]),
        text=str(args["text"]),
        topics=args.get("topics") or [],
        entities=args.get("entities") or [],
        source_refs=source_refs,
        importance=args.get("importance", 0.5),
        confidence=args.get("confidence", 0.7),
        expires_at=args.get("expires_at"),
        pinned_until=args.get("pinned_until"),
        publish_long_term=bool(args.get("publish_long_term", False)),
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
    )


def _tool_context_handoff(_args: Dict[str, Any]) -> Dict[str, Any]:
    return get_handoff()


def _tool_memory_recall(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    scope = _parse_scope_arguments(args, error_prefix="memory_recall")
    return recall_memory(
        query=str(args["query"]),
        limit=int(args.get("limit", 10)),
        memory_type=args.get("type"),
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
        include_long_term=bool(args.get("include_long_term", False)),
    )


def _tool_memory_stats(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = _parse_scope_arguments(args, error_prefix="memory_stats")
    return get_memory_stats(
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
    )


def _tool_memory_maintain(args: Dict[str, Any]) -> Dict[str, Any]:
    scope = _parse_scope_arguments(args, error_prefix="memory_maintain")
    if _parse_bool(args.get("enqueue", False)):
        job_id = enqueue_job("memory_maintain", "io", "memory:maintenance", "latest")
        return {"enqueued": True, "job_id": job_id}
    output = run_memory_maintenance(
        user_id=scope.get("user_id"),
        project_id=scope.get("project_id"),
        session_id=scope.get("session_id"),
    )
    output["enqueued"] = False
    return output


def _tool_voice_gallery_list(_args: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list_voiceprints()


def _tool_voice_gallery_update(args: Dict[str, Any]) -> Dict[str, Any]:
    vp_id = str(args["voiceprint_id"])
    fields = {k: v for k, v in args.items() if k != "voiceprint_id"}
    return upsert_person(vp_id, fields)


def _tool_voice_gallery_open(_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"resource_uri": "ui://voice-gallery"}


def _tool_ingest_auto(args: Dict[str, Any]) -> Dict[str, Any]:
    items = extract_items(
        text=str(args.get("text") or ""),
        items=args.get("items"),
        base_dir=None,
        dedupe=bool(args.get("dedupe", True)),
    )
    return {
        "items": enqueue_items(
            items,
            tags=args.get("tags"),
            context=str(args.get("context") or ""),
            speaker=str(args.get("speaker") or ""),
            organization=str(args.get("organization") or ""),
            event_date=str(args.get("event_date") or ""),
            source_metadata=args.get("source_metadata"),
        )
    }


def _tool_intake_open(_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"resource_uri": "ui://intake"}


def _resolve_obsidian_vault() -> Path:
    settings = load_settings()
    vault = settings.obsidian_vault_path
    if not vault:
        raise RuntimeError("OBSIDIAN_VAULT_PATH not set")
    resolved = Path(vault).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise RuntimeError(f"OBSIDIAN_VAULT_PATH is not a readable directory: {resolved}")
    return resolved


def _resolve_obsidian_path(raw_path: object, vault: Path) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise ValueError("note_path is required")
    candidate = Path(text).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (vault / candidate).resolve()
    if resolved != vault and vault not in resolved.parents:
        raise PermissionError(f"Path '{resolved}' is outside configured Obsidian vault '{vault}'")
    return resolved


def _tool_obsidian_watch_status(_args: Dict[str, Any]) -> Dict[str, Any]:
    settings = load_settings()
    vault = settings.obsidian_vault_path
    resolved = Path(vault).expanduser().resolve() if vault else None
    exists = bool(resolved and resolved.exists() and resolved.is_dir())
    return {
        "configured": bool(vault),
        "vault_path": str(resolved) if resolved else "",
        "vault_exists": exists,
        "watch_command": "./scripts/obsidian_watch.sh",
    }


def _tool_obsidian_list_notes(args: Dict[str, Any]) -> Dict[str, Any]:
    vault = _resolve_obsidian_vault()
    folder = str(args.get("folder") or "").strip()
    include_outputs = _parse_bool(args.get("include_outputs", False))
    limit = max(1, min(500, _to_int(args.get("limit") or 50)))

    base = _resolve_obsidian_path(folder, vault) if folder else vault
    if not base.exists() or not base.is_dir():
        raise FileNotFoundError(f"Folder not found in vault: {base}")

    candidates: List[Tuple[float, Path, int]] = []
    for note_path in base.rglob("*.md"):
        if not include_outputs:
            if note_path.name.endswith(".output.md"):
                continue
            if "_outputs" in note_path.parts:
                continue
        try:
            stat = note_path.stat()
        except Exception:
            continue
        candidates.append((float(stat.st_mtime), note_path, int(stat.st_size)))

    candidates.sort(key=lambda row: row[0], reverse=True)
    notes: List[Dict[str, Any]] = []
    for modified_at, note_path, size in candidates[:limit]:
        rel = str(note_path.relative_to(vault))
        notes.append(
            {
                "path": rel,
                "size_bytes": size,
                "updated_at": datetime.fromtimestamp(modified_at, tz=timezone.utc).isoformat(),
            }
        )

    folder_rel = ""
    if base != vault:
        folder_rel = str(base.relative_to(vault))
    return {
        "vault_path": str(vault),
        "folder": folder_rel,
        "count": len(notes),
        "notes": notes,
    }


def _tool_obsidian_enqueue_note(args: Dict[str, Any]) -> Dict[str, Any]:
    vault = _resolve_obsidian_vault()
    note_path = _resolve_obsidian_path(args.get("note_path"), vault)
    if note_path.suffix.lower() != ".md":
        raise ValueError("note_path must point to a .md note")
    if not note_path.exists() or not note_path.is_file():
        raise FileNotFoundError(f"Obsidian note not found: {note_path}")
    result = enqueue_obsidian_note(str(note_path))
    return {
        "vault_path": str(vault),
        "note_path": str(note_path),
        "note_rel_path": str(note_path.relative_to(vault)),
        "result": result,
    }


def _tool_dashboard_open(_args: Dict[str, Any]) -> Dict[str, Any]:
    return {"resource_uri": "ui://dashboard"}


def _parse_scope_arguments(args: Dict[str, Any], error_prefix: str) -> Dict[str, str]:
    settings = load_settings()
    defaults = {
        "user_id": normalize_identifier(settings.default_user_id, max_len=120) or None,
        "project_id": normalize_identifier(settings.default_project_id, max_len=120) or None,
        "session_id": normalize_identifier(settings.default_session_id, max_len=120) or None,
    }
    out: Dict[str, str] = {}
    for key in ("user_id", "project_id", "session_id"):
        value = args.get(key)
        if value is None:
            default_value = defaults.get(key)
            if default_value:
                out[key] = default_value
            continue
        if not isinstance(value, str):
            raise ValueError(f"{error_prefix}.{key} must be a string when provided")
        normalized = normalize_identifier(value, max_len=120)
        if normalized:
            out[key] = normalized
            continue
        default_value = defaults.get(key)
        if default_value:
            out[key] = default_value
    return out


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return False


def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    method = req.get("method")
    params = req.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": "2025-06-18",
            "capabilities": _mcp_capabilities(),
            "serverInfo": _mcp_server_info(),
        }
    if method in {"notifications/initialized", "initialized", "$/initialized", "ping"}:
        return {}
    if method == "tools/list":
        tools = _filter_tools_for_request(req, params)
        return {"tools": [_tool_for_mcp(tool) for tool in tools]}
    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tools/call requires params.name")
        _require_tool_allowed(name, req, params)
        args = params.get("arguments") or {}
        if name == "ingest_url":
            return _tool_ingest_url(args)
        if name == "ingest_doc":
            return _tool_ingest_doc(args)
        if name == "ingest_image":
            return _tool_ingest_image(args)
        if name == "ingest_youtube":
            return _tool_ingest_youtube(args)
        if name == "ask":
            return _tool_ask(args)
        if name == "memory_write":
            return _tool_memory_write(args)
        if name == "memory_recall":
            return _tool_memory_recall(args)
        if name == "memory_stats":
            return _tool_memory_stats(args)
        if name == "memory_maintain":
            return _tool_memory_maintain(args)
        if name == "context_handoff":
            return _tool_context_handoff(args)
        if name == "status":
            return _status()
        if name == "dashboard_stats":
            return _tool_dashboard_stats(args)
        if name == "dashboard_timeseries":
            return _tool_dashboard_timeseries(args)
        if name == "dashboard_alerts":
            return _tool_dashboard_alerts(args)
        if name == "dashboard_models":
            return _tool_dashboard_models(args)
        if name == "voice_gallery_list":
            return _tool_voice_gallery_list(args)
        if name == "voice_gallery_update":
            return _tool_voice_gallery_update(args)
        if name == "voice_gallery_open":
            return _tool_voice_gallery_open(args)
        if name == "ingest_auto":
            return _tool_ingest_auto(args)
        if name == "intake_open":
            return _tool_intake_open(args)
        if name == "obsidian_watch_status":
            return _tool_obsidian_watch_status(args)
        if name == "obsidian_list_notes":
            return _tool_obsidian_list_notes(args)
        if name == "obsidian_enqueue_note":
            return _tool_obsidian_enqueue_note(args)
        if name == "dashboard_open":
            return _tool_dashboard_open(args)
        raise ValueError(f"Unknown tool: {name}")
    if method == "resources/list":
        return {"resources": _resource_catalog()}
    if method in {"resources/get", "resources/read"}:
        uri = str(params.get("uri") or "").strip()
        mime_type, content = _read_resource(uri)
        if method == "resources/read":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": mime_type,
                        "mime_type": mime_type,
                        "text": content,
                        "content": content,
                    }
                ]
            }
        return {"uri": uri, "mime_type": mime_type, "mimeType": mime_type, "content": content}
    raise ValueError(f"Unknown method: {method}")


def _voice_gallery_html() -> str:
    # Minimal UI scaffold; editing is via voice_gallery_update tool.
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Voice Gallery</title>
  <style>
    body { font-family: Arial, sans-serif; padding: 16px; }
    h1 { margin: 0 0 12px; }
    pre { background: #f4f4f4; padding: 12px; }
  </style>
</head>
<body>
  <h1>Voice Gallery (EBUCore+)</h1>
  <p>Use MCP tools <code>voice_gallery_list</code> and <code>voice_gallery_update</code> to view/edit entries.</p>
  <p>Example update payload:</p>
  <pre>{
  "voiceprint_id": "...",
  "given_name": "",
  "family_name": "",
  "title": "",
  "role": "",
  "affiliation": "",
  "aliases": [],
  "tags": [],
  "notes": ""
}</pre>
</body>
</html>
"""


def _dashboard_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Aurora Dashboard</title>
  <style>
    :root {
      --bg: #f7f7f8;
      --ink: #14171f;
      --muted: #626b79;
      --card: #ffffff;
      --border: #e4e7ec;
      --ring: rgba(16, 163, 127, 0.2);
      --shadow: 0 12px 34px rgba(17, 24, 39, 0.07);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 24px;
      font-family: "Sohne", "Avenir Next", "IBM Plex Sans", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f9fafb 0%, var(--bg) 60%, #f5f6f8 100%);
    }
    .wrap { max-width: 940px; margin: 0 auto; display: grid; gap: 14px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 20px;
      box-shadow: var(--shadow);
      display: grid;
      gap: 12px;
    }
    h1 { margin: 0; font-size: clamp(28px, 4vw, 42px); letter-spacing: -0.02em; }
    p { margin: 0; color: var(--muted); font-size: 16px; line-height: 1.45; }
    button {
      border: 1px solid #d9dde6;
      border-radius: 999px;
      padding: 9px 14px;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      background: #fff;
      color: #223046;
    }
    button:hover { border-color: #bfc5d0; }
    .dash-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .dash-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
    .dash-tab.active { border-color: #111827; background: #111827; color: #fff; }
    .dash-panel { display: none; gap: 12px; }
    .dash-panel.active { display: grid; }
    .metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .metric { border: 1px solid var(--border); border-radius: 16px; padding: 12px; background: #f8fafc; display: grid; gap: 6px; }
    .metric-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; font-weight: 700; }
    .metric-value { font-size: 28px; line-height: 1.1; font-weight: 760; letter-spacing: -0.02em; }
    .metric-sub { font-size: 13px; color: var(--muted); }
    .progress-track { height: 10px; border-radius: 999px; background: #e6ebf1; overflow: hidden; }
    .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #111827 0%, #10a37f 100%); transition: width 180ms ease; }
    .dash-meta { display: grid; gap: 4px; font-size: 13px; color: #4b5563; }
    .dash-meta code { background: #f4f6f8; border: 1px solid #e2e8f0; border-radius: 6px; padding: 1px 5px; margin-right: 4px; }
    .spark-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .spark-card { border: 1px solid var(--border); border-radius: 14px; padding: 10px; background: #fff; display: grid; gap: 8px; }
    .spark-label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.03em; font-weight: 700; }
    .sparkline { height: 64px; display: flex; align-items: flex-end; gap: 3px; border-radius: 10px; background: #f8fafc; border: 1px solid #e6ecf3; padding: 6px; }
    .spark-bar { flex: 1 1 0; min-width: 2px; border-radius: 6px 6px 2px 2px; background: linear-gradient(180deg, #10a37f 0%, #0b7f64 100%); opacity: 0.88; }
    .alerts-list { display: grid; gap: 8px; }
    .alert-item { border-radius: 12px; border: 1px solid var(--border); padding: 10px 12px; background: #fff; display: grid; gap: 4px; }
    .alert-item.critical { border-color: #ef4444; background: #fff5f5; }
    .alert-item.high { border-color: #f97316; background: #fff8f1; }
    .alert-item.medium { border-color: #f59e0b; background: #fffbeb; }
    .alert-item.ok { border-color: #10b981; background: #f0fdf4; }
    .alert-title { font-size: 14px; font-weight: 700; }
    .alert-detail { color: #4b5563; font-size: 13px; }
    .models-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .model-card { border: 1px solid var(--border); border-radius: 14px; padding: 10px; background: #fff; display: grid; gap: 5px; }
    .model-name { font-size: 15px; font-weight: 700; }
    .mono-note { font-family: "IBM Plex Mono", "Menlo", monospace; font-size: 12px; color: #475569; }
    @media (max-width: 740px) {
      body { padding: 14px; }
      .card { border-radius: 18px; padding: 16px; }
      .metric-grid { grid-template-columns: 1fr; }
      .spark-grid { grid-template-columns: 1fr; }
      .models-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Aurora Dashboard</h1>
      <p>Live metrics for ingestion pipeline, vectorization, memory, alerts, and model/token estimates.</p>
    </div>
    <div class="card">
      <div class="dash-header">
        <div class="dash-tabs">
          <button class="dash-tab active" data-tab="overview">Overview</button>
          <button class="dash-tab" data-tab="pipeline">Pipeline</button>
          <button class="dash-tab" data-tab="alerts">Alerts</button>
          <button class="dash-tab" data-tab="models">Models</button>
        </div>
        <button id="refresh-dashboard">Refresh</button>
      </div>

      <div class="dash-panel active" data-panel="overview">
        <div class="metric-grid">
          <div class="metric">
            <div class="metric-label">Documents</div>
            <div class="metric-value" id="dash-docs-value">0</div>
            <div class="metric-sub" id="dash-docs-sub">Target: 0</div>
            <div class="progress-track"><div class="progress-fill" id="dash-docs-fill"></div></div>
          </div>
          <div class="metric">
            <div class="metric-label">Vectorization</div>
            <div class="metric-value" id="dash-vectors-value">0</div>
            <div class="metric-sub" id="dash-vectors-sub">Target: 0</div>
            <div class="progress-track"><div class="progress-fill" id="dash-vectors-fill"></div></div>
          </div>
          <div class="metric">
            <div class="metric-label">Agent Memory</div>
            <div class="metric-value" id="dash-memory-value">0</div>
            <div class="metric-sub" id="dash-memory-sub">Target: 0</div>
            <div class="progress-track"><div class="progress-fill" id="dash-memory-fill"></div></div>
          </div>
        </div>
        <div class="dash-meta">
          <div id="dash-queue">Queue: -</div>
          <div id="dash-memory-types">Memory types: -</div>
          <div id="dash-updated">Updated: -</div>
        </div>
      </div>

      <div class="dash-panel" data-panel="pipeline">
        <div class="spark-grid">
          <div class="spark-card"><div class="spark-label">Docs ingested (24h)</div><div class="sparkline" id="spark-docs"></div></div>
          <div class="spark-card"><div class="spark-label">Vectors built (24h)</div><div class="sparkline" id="spark-vectors"></div></div>
          <div class="spark-card"><div class="spark-label">Memory writes (24h)</div><div class="sparkline" id="spark-memory"></div></div>
          <div class="spark-card"><div class="spark-label">Jobs done vs failed (24h)</div><div class="sparkline" id="spark-jobs"></div></div>
        </div>
        <div class="dash-meta">
          <div id="pipeline-summary">Pipeline: -</div>
          <div class="mono-note" id="pipeline-window">Window: -</div>
        </div>
      </div>

      <div class="dash-panel" data-panel="alerts">
        <div class="alerts-list" id="alerts-list"></div>
        <div class="dash-meta"><div id="alerts-summary">Alerts: -</div></div>
      </div>

      <div class="dash-panel" data-panel="models">
        <div class="models-grid" id="models-grid"></div>
        <div class="dash-meta">
          <div id="models-summary">Models: -</div>
          <div id="models-codex-note" class="mono-note">Codex usage: -</div>
        </div>
      </div>
    </div>
  </div>
  <script>
    const dashTabs = Array.from(document.querySelectorAll(".dash-tab"));
    const dashPanels = Array.from(document.querySelectorAll(".dash-panel"));
    const refreshBtn = document.getElementById("refresh-dashboard");
    const dashDocsValue = document.getElementById("dash-docs-value");
    const dashDocsSub = document.getElementById("dash-docs-sub");
    const dashDocsFill = document.getElementById("dash-docs-fill");
    const dashVectorsValue = document.getElementById("dash-vectors-value");
    const dashVectorsSub = document.getElementById("dash-vectors-sub");
    const dashVectorsFill = document.getElementById("dash-vectors-fill");
    const dashMemoryValue = document.getElementById("dash-memory-value");
    const dashMemorySub = document.getElementById("dash-memory-sub");
    const dashMemoryFill = document.getElementById("dash-memory-fill");
    const dashQueue = document.getElementById("dash-queue");
    const dashMemoryTypes = document.getElementById("dash-memory-types");
    const dashUpdated = document.getElementById("dash-updated");
    const sparkDocs = document.getElementById("spark-docs");
    const sparkVectors = document.getElementById("spark-vectors");
    const sparkMemory = document.getElementById("spark-memory");
    const sparkJobs = document.getElementById("spark-jobs");
    const pipelineSummary = document.getElementById("pipeline-summary");
    const pipelineWindow = document.getElementById("pipeline-window");
    const alertsList = document.getElementById("alerts-list");
    const alertsSummary = document.getElementById("alerts-summary");
    const modelsGrid = document.getElementById("models-grid");
    const modelsSummary = document.getElementById("models-summary");
    const modelsCodexNote = document.getElementById("models-codex-note");

    function num(value) { const parsed = Number(value || 0); return Number.isFinite(parsed) ? parsed : 0; }
    function pct(value) { const parsed = num(value); return Math.max(0, Math.min(100, parsed)); }
    function fmtInt(value) { return num(value).toLocaleString("en-US"); }
    function clearChildren(el) { while (el && el.firstChild) el.removeChild(el.firstChild); }
    function renderBar(el, percent) { if (el) el.style.width = `${pct(percent)}%`; }
    function renderMap(data) {
      const entries = Object.entries(data || {});
      if (!entries.length) return "-";
      return entries.sort((a,b)=>String(a[0]).localeCompare(String(b[0]))).map(([k,v])=>`<code>${k}:${fmtInt(v)}</code>`).join(" ");
    }
    function setDashboardTab(tabName) {
      for (const tab of dashTabs) tab.classList.toggle("active", String(tab.dataset.tab || "") === tabName);
      for (const panel of dashPanels) panel.classList.toggle("active", String(panel.dataset.panel || "") === tabName);
    }
    function renderDashboard(stats) {
      const targets = stats && stats.targets ? stats.targets : {};
      const counts = stats && stats.counts ? stats.counts : {};
      const progress = stats && stats.progress ? stats.progress : {};
      dashDocsValue.textContent = fmtInt(counts.docs_total);
      dashDocsSub.textContent = `Target: ${fmtInt(targets.docs)} | ${pct(progress.docs_percent).toFixed(1)}%`;
      renderBar(dashDocsFill, progress.docs_percent);
      dashVectorsValue.textContent = fmtInt(counts.vectors_total);
      dashVectorsSub.textContent = `Target: ${fmtInt(targets.vectors)} | ${pct(progress.vectors_percent).toFixed(1)}%`;
      renderBar(dashVectorsFill, progress.vectors_percent);
      dashMemoryValue.textContent = fmtInt(counts.memory_total);
      dashMemorySub.textContent = `Target: ${fmtInt(targets.memory)} | ${pct(progress.memory_percent).toFixed(1)}%`;
      renderBar(dashMemoryFill, progress.memory_percent);
      dashQueue.innerHTML = `Queue: ${renderMap(stats.queue)}`;
      dashMemoryTypes.innerHTML = `Memory types: ${renderMap(counts.memory_by_type)}`;
      dashUpdated.textContent = `Updated: ${String(stats.updated_at || "-")}`;
    }
    function renderSparkline(el, values) {
      clearChildren(el);
      const safe = Array.isArray(values) ? values.map((x)=>num(x)) : [];
      if (!safe.length) { const empty = document.createElement("div"); empty.className = "mono-note"; empty.textContent = "No data"; el.appendChild(empty); return; }
      const maxValue = Math.max(1, ...safe);
      for (const value of safe) {
        const bar = document.createElement("div");
        bar.className = "spark-bar";
        bar.style.height = `${Math.max(6, Math.round((value / maxValue) * 100))}%`;
        bar.title = String(value);
        el.appendChild(bar);
      }
    }
    function renderTimeseries(series) {
      const buckets = Array.isArray(series && series.buckets) ? series.buckets : [];
      renderSparkline(sparkDocs, buckets.map((b)=>num(b.docs_ingested)));
      renderSparkline(sparkVectors, buckets.map((b)=>num(b.vectors_built)));
      renderSparkline(sparkMemory, buckets.map((b)=>num(b.memory_written)));
      renderSparkline(sparkJobs, buckets.map((b)=>num(b.jobs_done) + num(b.jobs_failed)));
      const totals = (series && series.totals) || {};
      pipelineSummary.innerHTML =
        `Pipeline totals: <code>docs:${fmtInt(totals.docs_ingested)}</code> <code>vectors:${fmtInt(totals.vectors_built)}</code> <code>memory:${fmtInt(totals.memory_written)}</code> <code>jobs_done:${fmtInt(totals.jobs_done)}</code> <code>jobs_failed:${fmtInt(totals.jobs_failed)}</code>`;
      pipelineWindow.textContent = `Window: last ${fmtInt(series.window_hours)}h, bucket ${fmtInt(series.bucket_minutes)}m`;
    }
    function renderAlerts(payload) {
      const alerts = Array.isArray(payload && payload.alerts) ? payload.alerts : [];
      clearChildren(alertsList);
      for (const item of alerts) {
        const wrap = document.createElement("div");
        const severity = String(item && item.severity ? item.severity : "medium");
        wrap.className = `alert-item ${severity}`;
        const title = document.createElement("div");
        title.className = "alert-title";
        title.textContent = `${String(severity).toUpperCase()} • ${String(item.title || "Alert")}`;
        const detail = document.createElement("div");
        detail.className = "alert-detail";
        detail.textContent = String(item.detail || "");
        wrap.appendChild(title); wrap.appendChild(detail); alertsList.appendChild(wrap);
      }
      const summary = (payload && payload.summary) || {};
      alertsSummary.innerHTML = `Alerts summary: <code>stale:${fmtInt(summary.running_stale)}</code> <code>retry:${fmtInt(summary.queued_retries)}</code> <code>recent_errors:${fmtInt(summary.recent_errors)}</code>`;
    }
    function renderModels(payload) {
      const models = Array.isArray(payload && payload.models) ? payload.models : [];
      clearChildren(modelsGrid);
      for (const model of models) {
        const card = document.createElement("div");
        card.className = "model-card";
        card.innerHTML = `
          <div class="model-name">${String(model.model || "unknown")}</div>
          <div class="mono-note">requests=${fmtInt(model.requests)} errors=${fmtInt(model.errors)} err_rate=${num(model.error_rate_pct).toFixed(2)}%</div>
          <div class="mono-note">prompt_tok_est=${fmtInt(model.prompt_tokens_est)} completion_tok_est=${fmtInt(model.completion_tokens_est)}</div>
          <div class="mono-note">components: ${renderMap(model.components)}</div>`;
        modelsGrid.appendChild(card);
      }
      const summary = (payload && payload.summary) || {};
      modelsSummary.textContent =
        `Models summary: requests=${fmtInt(summary.requests)} errors=${fmtInt(summary.errors)} prompt_tok_est=${fmtInt(summary.prompt_tokens_est)} completion_tok_est=${fmtInt(summary.completion_tokens_est)}`;
      const codexUsage = (payload && payload.codex_usage) || {};
      modelsCodexNote.textContent = codexUsage.available ? "Codex usage: available" : `Codex usage: ${String(codexUsage.reason || "not available")}`;
    }
    async function callTool(name, args) {
      if (window.mcp && window.mcp.tools && window.mcp.tools.call) return window.mcp.tools.call(name, args);
      if (window.mcp && window.mcp.callTool) return window.mcp.callTool({ name: name, arguments: args });
      const isHttp = window.location && /^https?:$/i.test(window.location.protocol || "");
      if (isHttp) {
        const resp = await fetch("/api/tools/call", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name, arguments: args || {} }) });
        const payload = await resp.json();
        if (!resp.ok || payload.error) throw new Error(String((payload && payload.error) || `HTTP ${resp.status}`));
        return payload.result || payload;
      }
      throw new Error("MCP tool bridge not available. Run via MCP client or local dashboard server.");
    }
    async function refreshDashboard() {
      try {
        const [stats, series, alerts, models] = await Promise.all([
          callTool("dashboard_stats", {}),
          callTool("dashboard_timeseries", { window_hours: 24, bucket_minutes: 60 }),
          callTool("dashboard_alerts", { stale_running_minutes: 20, error_window_hours: 24 }),
          callTool("dashboard_models", { window_hours: 24 }),
        ]);
        renderDashboard(stats || {});
        renderTimeseries(series || {});
        renderAlerts(alerts || {});
        renderModels(models || {});
      } catch (err) {
        dashQueue.textContent = `Queue: error (${String(err)})`;
        pipelineSummary.textContent = `Pipeline: error (${String(err)})`;
        alertsSummary.textContent = `Alerts: error (${String(err)})`;
        modelsSummary.textContent = `Models: error (${String(err)})`;
      }
    }
    for (const tab of dashTabs) tab.addEventListener("click", () => setDashboardTab(String(tab.dataset.tab || "overview")));
    refreshBtn.addEventListener("click", refreshDashboard);
    setDashboardTab("overview");
    refreshDashboard();
    setInterval(refreshDashboard, 15000);
  </script>
</body>
</html>
"""


def _intake_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Aurora Intake</title>
  <style>
    :root {
      --bg: #f7f7f8;
      --ink: #14171f;
      --muted: #626b79;
      --accent: #10a37f;
      --card: #ffffff;
      --border: #e4e7ec;
      --ring: rgba(16, 163, 127, 0.2);
      --shadow: 0 12px 34px rgba(17, 24, 39, 0.07);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Sohne", "Avenir Next", "IBM Plex Sans", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f9fafb 0%, var(--bg) 60%, #f5f6f8 100%);
      padding: 24px;
    }
    .wrap {
      max-width: 940px;
      margin: 0 auto;
      display: grid;
      gap: 16px;
      animation: rise 0.5s ease-out;
    }
    @keyframes rise {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px;
      box-shadow: var(--shadow);
    }
    h1 {
      margin: 0 0 10px;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1.06;
      letter-spacing: -0.02em;
      max-width: 20ch;
    }
    p {
      margin: 0;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.45;
    }
    textarea {
      width: 100%;
      min-height: 190px;
      border-radius: 18px;
      border: 1px solid var(--border);
      padding: 16px 18px;
      font-size: 17px;
      line-height: 1.5;
      font-family: "IBM Plex Mono", "Menlo", "Consolas", monospace;
      background: #ffffff;
      color: #222831;
      resize: vertical;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }
    textarea:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 4px var(--ring);
    }
    .meta-input {
      width: 100%;
      border-radius: 12px;
      border: 1px solid var(--border);
      padding: 10px 12px;
      font-size: 14px;
      font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
      background: #ffffff;
      color: #223046;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }
    .meta-input:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--ring);
    }
    .context-input {
      min-height: 96px;
      font-family: "IBM Plex Sans", "Avenir Next", sans-serif;
      font-size: 14px;
    }
    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 6px;
    }
    button {
      -webkit-appearance: none;
      appearance: none;
      border: 1px solid #d9dde6;
      border-radius: 999px;
      padding: 11px 18px;
      font-weight: 700;
      font-size: 17px;
      cursor: pointer;
      background: #ffffff;
      color: #223046;
      transition: transform 100ms ease, filter 120ms ease, border-color 120ms ease, background 120ms ease, color 120ms ease;
    }
    button:hover {
      border-color: #bfc5d0;
      transform: translateY(-1px);
    }
    .actions .action-btn.selected,
    .modal-actions .action-btn.selected {
      background: var(--accent) !important;
      color: #ffffff !important;
      border-color: var(--accent) !important;
      box-shadow: 0 0 0 4px var(--ring);
    }
    .actions .action-btn:active,
    .modal-actions .action-btn:active {
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }
    .status {
      margin-top: 12px;
      color: #4b5563;
      font-size: 15px;
    }
    .selected-label {
      margin-top: -2px;
      color: #0f6a52;
      font-size: 14px;
      font-weight: 700;
      min-height: 20px;
    }
    pre {
      margin: 0;
      background: #fafafa;
      border: 1px solid var(--border);
      padding: 14px;
      border-radius: 16px;
      overflow: auto;
      font-size: 14px;
      color: #1f2937;
    }
    .grid {
      display: grid;
      gap: 12px;
    }
    .dropzone {
      border: 1px dashed #cdd3dd;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }
    .dropzone.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 4px var(--ring);
    }
    .hint {
      margin: 0;
      font-size: 15px;
      color: var(--muted);
    }
    .badge {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 999px;
      background: #eff3f7;
      color: #344256;
      font-size: 12px;
      margin-left: 8px;
      border: 1px solid #dbe1ea;
    }
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(17, 24, 39, 0.44);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .modal.active { display: flex; }
    .modal-card {
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 18px 18px 16px;
      width: min(420px, 100%);
      box-shadow: 0 24px 52px rgba(17,24,39,0.22);
      display: grid;
      gap: 10px;
    }
    .modal-card p { font-size: 15px; }
    .modal-actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .guide {
      display: grid;
      gap: 8px;
      font-size: 14px;
      color: var(--muted);
    }
    .guide b { color: var(--ink); }
    @media (max-width: 740px) {
      body { padding: 14px; }
      .card { border-radius: 18px; padding: 16px; }
      p { font-size: 16px; }
      textarea { min-height: 160px; font-size: 16px; }
      button { font-size: 16px; padding: 10px 15px; }
      .actions { gap: 8px; }
      .hint { font-size: 14px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Paste or drop files/links to ingest</h1>
      <p>YouTube links auto-transcribe. Other URLs ingest as readable text. You can also drop files from Finder.</p>
    </div>
    <div class="card grid">
      <textarea class="dropzone" id="input" placeholder="https://youtu.be/...&#10;https://example.com/article&#10;/Users/name/Documents/report.pdf"></textarea>
      <input class="meta-input" id="tags" placeholder="Optional tags (comma-separated): policy, ai, python" />
      <textarea class="meta-input context-input" id="context" placeholder="Optional context to attach at ingest start (applies to all pasted items)."></textarea>
      <input class="meta-input" id="speaker" placeholder="Optional speaker (e.g. Philipp Roth)" />
      <input class="meta-input" id="organization" placeholder="Optional organization (e.g. ORF)" />
      <input class="meta-input" id="event-date" placeholder="Optional date (YYYY-MM-DD)" />
      <p class="hint">Tip: drag files from Finder here, or click Add files/folder.</p>
      <input id="file-picker" type="file" multiple style="display:none" />
      <input id="folder-picker" type="file" webkitdirectory directory multiple style="display:none" />
      <div class="actions">
        <button id="pick-files">Add files</button>
        <button id="pick-folder">Add folder</button>
        <button id="action-import" class="action-btn">Importera</button>
        <button id="action-ask" class="action-btn">Fraga</button>
        <button id="action-remember" class="action-btn">Kom ihag</button>
        <button id="action-todo" class="action-btn">TODO</button>
        <button id="clear">Clear</button>
      </div>
      <div class="status" id="status">Ready.</div>
      <div class="selected-label" id="selected-label">Selected: none</div>
    </div>
    <div class="card grid">
      <strong>What the buttons mean</strong>
      <div class="guide">
        <div><b>Importera:</b> Indexes pasted links/files into Aurora knowledge base.</div>
        <div><b>Fraga:</b> Asks Aurora a question using current text as the prompt.</div>
        <div><b>Kom ihag:</b> Saves text as memory via Aurora remember flow.</div>
        <div><b>TODO:</b> Saves text as a TODO memory item so you can recall it later.</div>
      </div>
    </div>
    <div class="card grid">
      <div>
        <strong>Results</strong>
        <span class="badge">ingest_auto</span>
      </div>
      <pre id="output">{}</pre>
    </div>
  </div>
  <div class="modal" id="prompt">
    <div class="modal-card">
      <strong>What do you want to do?</strong>
      <p>Choose how to process the pasted text.</p>
      <div class="modal-actions">
        <button id="prompt-import" class="action-btn">Importera</button>
        <button id="prompt-ask" class="action-btn">Fraga</button>
        <button id="prompt-remember" class="action-btn">Kom ihag</button>
        <button id="prompt-todo" class="action-btn">TODO</button>
        <button id="prompt-cancel">Cancel</button>
      </div>
    </div>
  </div>
  <script>
    const statusEl = document.getElementById("status");
    const outputEl = document.getElementById("output");
    const inputEl = document.getElementById("input");
    const tagsEl = document.getElementById("tags");
    const contextEl = document.getElementById("context");
    const speakerEl = document.getElementById("speaker");
    const organizationEl = document.getElementById("organization");
    const eventDateEl = document.getElementById("event-date");
    const importBtn = document.getElementById("action-import");
    const askBtn = document.getElementById("action-ask");
    const rememberBtn = document.getElementById("action-remember");
    const todoBtn = document.getElementById("action-todo");
    const clearBtn = document.getElementById("clear");
    const pickFilesBtn = document.getElementById("pick-files");
    const pickFolderBtn = document.getElementById("pick-folder");
    const filePicker = document.getElementById("file-picker");
    const folderPicker = document.getElementById("folder-picker");
    const promptEl = document.getElementById("prompt");
    const promptImport = document.getElementById("prompt-import");
    const promptAsk = document.getElementById("prompt-ask");
    const promptRemember = document.getElementById("prompt-remember");
    const promptTodo = document.getElementById("prompt-todo");
    const promptCancel = document.getElementById("prompt-cancel");
    const selectedLabelEl = document.getElementById("selected-label");
    const actionButtons = [importBtn, askBtn, rememberBtn, todoBtn, promptImport, promptAsk, promptRemember, promptTodo].filter(Boolean);
    let dragDepth = 0;

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function setOutput(data) {
      outputEl.textContent = JSON.stringify(data, null, 2);
    }

    function markSelected(action) {
      for (const btn of actionButtons) {
        btn.classList.remove("selected");
        btn.setAttribute("data-selected", "false");
        btn.style.backgroundColor = "";
        btn.style.color = "";
        btn.style.borderColor = "";
      }
      const map = {
        import: [importBtn, promptImport],
        ask: [askBtn, promptAsk],
        remember: [rememberBtn, promptRemember],
        todo: [todoBtn, promptTodo],
      };
      const labels = {
        import: "Importera",
        ask: "Fraga",
        remember: "Kom ihag",
        todo: "TODO",
      };
      const targets = map[action] || [];
      for (const btn of targets) {
        if (!btn) {
          continue;
        }
        btn.classList.add("selected");
        btn.setAttribute("data-selected", "true");
        btn.style.backgroundColor = "var(--accent)";
        btn.style.color = "#ffffff";
        btn.style.borderColor = "var(--accent)";
      }
      if (selectedLabelEl) {
        selectedLabelEl.textContent = action ? `Selected: ${labels[action]}` : "Selected: none";
      }
    }

    function unique(values) {
      const seen = new Set();
      const out = [];
      for (const value of values) {
        const item = String(value || "").trim();
        if (!item || seen.has(item)) {
          continue;
        }
        seen.add(item);
        out.push(item);
      }
      return out;
    }

    function parseTags(raw) {
      const out = [];
      const seen = new Set();
      for (const token of String(raw || "").replace(/\\n/g, ",").split(",")) {
        const tag = token.trim();
        if (!tag) {
          continue;
        }
        const key = tag.toLowerCase();
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        out.push(tag);
      }
      return out;
    }

    function appendItems(items) {
      const values = unique(items);
      if (!values.length) {
        return 0;
      }
      const before = inputEl.value.trim();
      inputEl.value = before ? `${before}\\n${values.join("\\n")}` : values.join("\\n");
      return values.length;
    }

    function parseUriList(raw) {
      const out = [];
      for (const line of String(raw || "").split("\\n")) {
        const value = line.trim();
        if (!value || value.startsWith("#")) {
          continue;
        }
        out.push(value);
      }
      return out;
    }

    function parsePlainText(raw) {
      const out = [];
      for (const line of String(raw || "").split("\\n")) {
        const value = line.trim();
        if (!value) {
          continue;
        }
        if (
          value.startsWith("http://") ||
          value.startsWith("https://") ||
          value.startsWith("file://") ||
          value.startsWith("/") ||
          value.startsWith("~") ||
          /^[A-Za-z]:\\//.test(value)
        ) {
          out.push(value);
        }
      }
      return out;
    }

    function pathsFromFileList(fileList) {
      const out = [];
      let unresolved = 0;
      for (const file of Array.from(fileList || [])) {
        const rawPath = typeof file.path === "string" ? file.path.trim() : "";
        if (rawPath) {
          out.push(rawPath);
        } else {
          unresolved += 1;
        }
      }
      return { paths: out, unresolved };
    }

    function closeDropState() {
      dragDepth = 0;
      inputEl.classList.remove("active");
    }

    function collectDropItems(event) {
      const transfer = event.dataTransfer;
      if (!transfer) {
        return { items: [], unresolved: 0 };
      }
      const items = [];
      items.push(...parseUriList(transfer.getData("text/uri-list")));
      items.push(...parsePlainText(transfer.getData("text/plain")));
      const fromFiles = pathsFromFileList(transfer.files);
      items.push(...fromFiles.paths);
      return { items: unique(items), unresolved: fromFiles.unresolved };
    }

    function addFromPicker(fileList) {
      const parsed = pathsFromFileList(fileList);
      const added = appendItems(parsed.paths);
      if (added > 0) {
        setStatus(`Added ${added} item(s). Click Importera.`);
      } else if (parsed.unresolved > 0) {
        setStatus("Picker opened, but absolute paths were not exposed. Drag from Finder or paste file paths.");
      } else {
        setStatus("No files selected.");
      }
    }

    async function callTool(name, args) {
      if (window.mcp && window.mcp.tools && window.mcp.tools.call) {
        return window.mcp.tools.call(name, args);
      }
      if (window.mcp && window.mcp.callTool) {
        return window.mcp.callTool({ name: name, arguments: args });
      }
      const isHttp = window.location && /^https?:$/i.test(window.location.protocol || "");
      if (isHttp) {
        const resp = await fetch("/api/tools/call", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: name, arguments: args || {} }),
        });
        let payload = {};
        try {
          payload = await resp.json();
        } catch (_err) {
          payload = {};
        }
        if (!resp.ok || payload.error) {
          throw new Error(String((payload && payload.error) || `HTTP ${resp.status}`));
        }
        return payload.result || payload;
      }
      throw new Error("MCP tool bridge not available. Open this UI from MCP or via http://127.0.0.1:8765/.");
    }

    async function doIngest() {
      const text = inputEl.value.trim();
      if (!text) {
        setStatus("Paste one or more links first.");
        return;
      }
      setStatus("Enqueuing...");
      try {
        const tags = parseTags(tagsEl ? tagsEl.value : "");
        const context = contextEl ? String(contextEl.value || "").trim() : "";
        const speaker = speakerEl ? String(speakerEl.value || "").trim() : "";
        const organization = organizationEl ? String(organizationEl.value || "").trim() : "";
        const eventDate = eventDateEl ? String(eventDateEl.value || "").trim() : "";
        const result = await callTool("ingest_auto", {
          text: text,
          tags: tags,
          context: context,
          speaker: speaker,
          organization: organization,
          event_date: eventDate,
        });
        setOutput(result);
        setStatus("Queued. You can close this window.");
      } catch (err) {
        setOutput({ error: String(err) });
        setStatus("Unable to call MCP tool. Use ingest_auto manually.");
      }
    }

    async function doAsk() {
      const text = inputEl.value.trim();
      if (!text) {
        setStatus("Paste a question first.");
        return;
      }
      setStatus("Asking...");
      try {
        const result = await callTool("ask", { question: text });
        setOutput(result);
        setStatus("Done.");
      } catch (err) {
        setOutput({ error: String(err) });
        setStatus("Unable to call MCP tool.");
      }
    }

    function rememberPrompt(text) {
      const value = String(text || "").trim();
      if (!value) {
        return "";
      }
      if (/^(remember(?:\\s+this|\\s+that)?|kom\\s+ih[ag](?:\\s+(?:detta|det\\s+har))?)\\s*[:\\-]?/i.test(value)) {
        return value;
      }
      return `kom ihag detta: ${value}`;
    }

    async function doRemember() {
      const text = inputEl.value.trim();
      if (!text) {
        setStatus("Paste memory text first.");
        return;
      }
      setStatus("Saving memory...");
      try {
        const result = await callTool("ask", { question: rememberPrompt(text), intent: "remember" });
        setOutput(result);
        setStatus("Memory saved.");
      } catch (err) {
        setOutput({ error: String(err) });
        setStatus("Unable to call MCP tool.");
      }
    }

    async function doTodo() {
      const text = inputEl.value.trim();
      if (!text) {
        setStatus("Paste TODO text first.");
        return;
      }
      const todoText = /^todo:/i.test(text) ? text : `TODO: ${text}`;
      setStatus("Saving TODO...");
      try {
        const result = await callTool("memory_write", {
          type: "working",
          text: todoText,
          topics: ["todo", "intake_ui"],
          source_refs: { kind: "intake_todo" },
          importance: 0.9,
          confidence: 0.9,
          intent: "todo",
        });
        setOutput(result);
        setStatus("TODO saved.");
      } catch (err) {
        setOutput({ error: String(err) });
        setStatus("Unable to call MCP tool.");
      }
    }

    function openPrompt() {
      promptEl.classList.add("active");
    }

    function closePrompt() {
      promptEl.classList.remove("active");
    }

    inputEl.addEventListener("paste", () => {
      setTimeout(() => {
        if (inputEl.value.trim()) {
          openPrompt();
        }
      }, 0);
    });
    inputEl.addEventListener("dragenter", (event) => {
      event.preventDefault();
      dragDepth += 1;
      inputEl.classList.add("active");
    });
    inputEl.addEventListener("dragover", (event) => {
      event.preventDefault();
    });
    inputEl.addEventListener("dragleave", (event) => {
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) {
        inputEl.classList.remove("active");
      }
    });
    inputEl.addEventListener("drop", (event) => {
      event.preventDefault();
      closeDropState();
      const parsed = collectDropItems(event);
      const added = appendItems(parsed.items);
      if (added > 0) {
        setStatus(`Added ${added} dropped item(s). Click Importera.`);
        openPrompt();
      } else if (parsed.unresolved > 0) {
        setStatus("Drop detected, but client hid file paths. Try dragging from Finder or paste absolute paths.");
      } else {
        setStatus("Drop detected, but no importable items found.");
      }
    });

    importBtn.addEventListener("click", async () => {
      markSelected("import");
      await doIngest();
    });
    askBtn.addEventListener("click", async () => {
      markSelected("ask");
      await doAsk();
    });
    rememberBtn.addEventListener("click", async () => {
      markSelected("remember");
      await doRemember();
    });
    todoBtn.addEventListener("click", async () => {
      markSelected("todo");
      await doTodo();
    });
    pickFilesBtn.addEventListener("click", () => filePicker.click());
    pickFolderBtn.addEventListener("click", () => folderPicker.click());
    filePicker.addEventListener("change", () => {
      addFromPicker(filePicker.files);
      filePicker.value = "";
    });
    folderPicker.addEventListener("change", () => {
      addFromPicker(folderPicker.files);
      folderPicker.value = "";
    });
    promptImport.addEventListener("click", async () => {
      closePrompt();
      markSelected("import");
      await doIngest();
    });
    promptAsk.addEventListener("click", async () => {
      closePrompt();
      markSelected("ask");
      await doAsk();
    });
    promptRemember.addEventListener("click", async () => {
      closePrompt();
      markSelected("remember");
      await doRemember();
    });
    promptTodo.addEventListener("click", async () => {
      closePrompt();
      markSelected("todo");
      await doTodo();
    });
    promptCancel.addEventListener("click", closePrompt);

    clearBtn.addEventListener("click", () => {
      inputEl.value = "";
      if (tagsEl) tagsEl.value = "";
      if (contextEl) contextEl.value = "";
      if (speakerEl) speakerEl.value = "";
      if (organizationEl) organizationEl.value = "";
      if (eventDateEl) eventDateEl.value = "";
      closeDropState();
      setOutput({});
      setStatus("Cleared.");
      markSelected("");
    });
  </script>
</body>
</html>
"""


def main() -> None:
    configure_logging()
    init_db()
    background_handle = start_background_checkpoint()
    try:
        for req, framed in _iter_requests():
            req_id = req.get("id")
            is_notification = req_id is None
            try:
                result = handle_request(req)
                if is_notification:
                    continue
                resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            except Exception as exc:
                if is_notification:
                    continue
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(exc)}}
            _write_response(resp, framed=framed)
    finally:
        stop_background_checkpoint(background_handle)


def _iter_requests() -> Iterator[Tuple[Dict[str, Any], bool]]:
    stream = sys.stdin.buffer
    while True:
        first = stream.readline()
        if not first:
            return
        if not first.strip():
            continue
        stripped = first.lstrip()
        if stripped.startswith(b"{") or stripped.startswith(b"["):
            req = _try_parse_request(first.decode("utf-8", errors="replace"))
            if req is not None:
                yield req, False
            continue

        headers: Dict[str, str] = {}
        line = first.decode("utf-8", errors="replace").strip()
        while line:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
            next_line = stream.readline()
            if not next_line:
                line = ""
                break
            line = next_line.decode("utf-8", errors="replace").strip()

        raw_len = headers.get("content-length", "0").strip()
        try:
            content_length = int(raw_len)
        except Exception:
            content_length = 0
        if content_length <= 0:
            continue
        payload = stream.read(content_length)
        if not payload:
            return
        req = _try_parse_request(payload.decode("utf-8", errors="replace"))
        if req is not None:
            yield req, True


def _try_parse_request(raw: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _write_response(resp: Dict[str, Any], framed: bool) -> None:
    payload = json.dumps(resp, ensure_ascii=True).encode("utf-8")
    out = sys.stdout.buffer
    if framed:
        out.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii"))
        out.write(payload)
    else:
        out.write(payload + b"\n")
    out.flush()
