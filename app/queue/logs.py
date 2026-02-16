"""Run log utilities."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from app.core.config import load_settings
from app.queue.db import get_conn


def log_run(lane: str, component: str, input_json: Optional[Dict[str, Any]] = None, output_json: Optional[Dict[str, Any]] = None, model: Optional[str] = None, error: Optional[str] = None) -> str:
    run_id = str(uuid.uuid4())
    settings = load_settings()
    input_payload = _serialize_log_payload(input_json or {}, settings.run_log_max_json_chars, "input_json")
    output_payload = _serialize_log_payload(output_json or {}, settings.run_log_max_json_chars, "output_json")
    error_text = _truncate_error(error, settings.run_log_max_error_chars)
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "INSERT INTO run_log (run_id, created_at, lane, component, model, input_json, output_json, error) "
                "VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    lane,
                    component,
                    model,
                    input_payload,
                    output_payload,
                    error_text,
                ),
            )
        else:
            cur.execute(
                "INSERT INTO run_log (run_id, created_at, lane, component, model, input_json, output_json, error) "
                "VALUES (%s, now(), %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    lane,
                    component,
                    model,
                    input_payload,
                    output_payload,
                    error_text,
                ),
            )
        conn.commit()
    return run_id


def _serialize_log_payload(payload: object, max_chars: int, field_name: str) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
    if len(encoded) <= max_chars:
        return encoded

    preview_len = max(60, max_chars - 220)
    note = f"{field_name} truncated to {max_chars} chars"
    while True:
        wrapped = {
            "truncated": True,
            "field": field_name,
            "raw_chars": len(encoded),
            "note": note,
            "preview": encoded[:preview_len],
        }
        rendered = json.dumps(wrapped, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        if len(rendered) <= max_chars or preview_len <= 60:
            return rendered
        preview_len = max(60, preview_len - 40)


def _truncate_error(error: Optional[str], max_chars: int) -> Optional[str]:
    if error is None:
        return None
    value = str(error)
    if len(value) <= max_chars:
        return value
    suffix = "...<truncated>"
    keep = max(0, max_chars - len(suffix))
    return value[:keep] + suffix
