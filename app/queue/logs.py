"""Run log utilities."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from app.queue.db import get_conn


def log_run(lane: str, component: str, input_json: Optional[Dict[str, Any]] = None, output_json: Optional[Dict[str, Any]] = None, model: Optional[str] = None, error: Optional[str] = None) -> str:
    run_id = str(uuid.uuid4())
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
                    json.dumps(input_json or {}),
                    json.dumps(output_json or {}),
                    error,
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
                    json.dumps(input_json or {}),
                    json.dumps(output_json or {}),
                    error,
                ),
            )
        conn.commit()
    return run_id
