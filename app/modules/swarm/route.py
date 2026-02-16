"""Route a question using fast model."""

from __future__ import annotations

import re

from app.core.textnorm import normalize_user_text
from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.models import RouteOutput
from app.queue.logs import log_run


def _prompt(question: str) -> str:
    return (
        "Return ONLY valid JSON with keys: intent, filters, retrieve_top_k, "
        "need_strong_model, reason. "
        "filters may include: topics (array), entities (array), source_type, "
        "memory_type, memory_kind, date_from, date_to. "
        "retrieve_top_k should be an integer. need_strong_model is boolean.\n\n"
        f"Question:\n{question}\n"
    )


def route_question(question: str) -> RouteOutput:
    raw_question = str(question or "")
    question = normalize_user_text(raw_question, max_len=2400)
    norm_meta = {
        "question_len_raw": len(raw_question),
        "question_len": len(question),
        "question_truncated": len(question) < len(raw_question),
    }
    settings = load_settings()
    run_id = log_run(
        lane="oss20b",
        component="swarm_route",
        input_json={"question": question, **norm_meta},
        model=settings.ollama_model_fast,
    )
    try:
        output = _sanitize_route_output(generate_json(_prompt(question), settings.ollama_model_fast, RouteOutput))
        log_run(lane="oss20b", component="swarm_route", input_json={"run_id": run_id}, output_json=output.model_dump())
        return output
    except Exception as exc:
        log_run(lane="oss20b", component="swarm_route", input_json={"run_id": run_id}, error=str(exc))
        return RouteOutput(
            intent="ask",
            filters={},
            retrieve_top_k=8,
            need_strong_model=False,
            reason=f"fallback_route:{exc}",
        )


def _sanitize_route_output(output: RouteOutput) -> RouteOutput:
    return RouteOutput(
        intent=normalize_user_text(output.intent or "ask", max_len=80) or "ask",
        filters=_sanitize_filters(output.filters),
        retrieve_top_k=_clamp_int(output.retrieve_top_k, default=8, low=1, high=20),
        need_strong_model=bool(output.need_strong_model),
        reason=normalize_user_text(output.reason, max_len=320) if output.reason else None,
    )


def _sanitize_filters(filters: object) -> dict:
    if not isinstance(filters, dict):
        return {}

    out = {}
    topics = _sanitize_text_list(filters.get("topics"), max_items=10, max_len=80)
    entities = _sanitize_text_list(filters.get("entities"), max_items=10, max_len=80)
    source_type = normalize_user_text(filters.get("source_type"), max_len=40)
    memory_type = normalize_user_text(filters.get("memory_type"), max_len=20)
    memory_kind = _sanitize_memory_kind(filters.get("memory_kind"))
    date_from = _sanitize_date(filters.get("date_from"))
    date_to = _sanitize_date(filters.get("date_to"))

    if topics:
        out["topics"] = topics
    if entities:
        out["entities"] = entities
    if source_type:
        out["source_type"] = source_type
    if memory_type:
        out["memory_type"] = memory_type
    if memory_kind:
        out["memory_kind"] = memory_kind
    if date_from:
        out["date_from"] = date_from
    if date_to:
        out["date_to"] = date_to
    return out


def _sanitize_text_list(values: object, max_items: int, max_len: int) -> list[str]:
    if not isinstance(values, list):
        return []
    out = []
    seen = set()
    for item in values:
        text = normalize_user_text(item, max_len=max_len)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= max_items:
            break
    return out


def _sanitize_date(value: object) -> str | None:
    text = normalize_user_text(value, max_len=30)
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    return None


def _clamp_int(value: object, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    if parsed < low:
        return low
    if parsed > high:
        return high
    return parsed


def _sanitize_memory_kind(value: object) -> str | None:
    text = normalize_user_text(value, max_len=20).lower()
    if text in {"semantic", "episodic", "procedural"}:
        return text
    return None
