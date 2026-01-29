"""Job queue operations."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.queue.db import get_conn


def enqueue_job(job_type: str, lane: str, source_id: str, source_version: str, next_run_at: Optional[datetime] = None) -> str:
    job_id = str(uuid.uuid4())
    next_run_at = next_run_at or datetime.now(timezone.utc)

    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "INSERT INTO jobs (job_id, job_type, lane, status, source_id, source_version, attempts, next_run_at, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?, 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (job_id, job_type, lane, source_id, source_version, next_run_at.isoformat()),
            )
        else:
            cur.execute(
                "INSERT INTO jobs (job_id, job_type, lane, status, source_id, source_version, attempts, next_run_at, created_at, updated_at) "
                "VALUES (%s, %s, %s, 'queued', %s, %s, 0, %s, now(), now())",
                (job_id, job_type, lane, source_id, source_version, next_run_at),
            )
        conn.commit()

    return job_id


def claim_job(lane: str, lock_seconds: int = 300) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    lock_until = now + timedelta(seconds=lock_seconds)

    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute(
                "SELECT job_id, job_type, lane, status, source_id, source_version, attempts, next_run_at "
                "FROM jobs WHERE lane=? AND status='queued' AND next_run_at<=? ORDER BY created_at LIMIT 1",
                (lane, now.isoformat()),
            )
            row = cur.fetchone()
            if not row:
                return None
            job_id = row[0]
            cur.execute(
                "UPDATE jobs SET status='running', locked_until=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (lock_until.isoformat(), job_id),
            )
            conn.commit()
        else:
            cur.execute(
                "SELECT job_id, job_type, lane, status, source_id, source_version, attempts, next_run_at "
                "FROM jobs WHERE lane=%s AND status='queued' AND next_run_at<=now() "
                "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1",
                (lane,),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            job_id = row[0]
            cur.execute(
                "UPDATE jobs SET status='running', locked_until=%s, updated_at=now() WHERE job_id=%s",
                (lock_until, job_id),
            )
            conn.commit()

    return {
        "job_id": row[0],
        "job_type": row[1],
        "lane": row[2],
        "status": row[3],
        "source_id": row[4],
        "source_version": row[5],
        "attempts": row[6],
        "next_run_at": row[7],
    }


def mark_done(job_id: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute("UPDATE jobs SET status='done', updated_at=CURRENT_TIMESTAMP WHERE job_id=?", (job_id,))
        else:
            cur.execute("UPDATE jobs SET status='done', updated_at=now() WHERE job_id=%s", (job_id,))
        conn.commit()


def mark_failed(job_id: str, error: str, max_attempts: int = 3) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        if conn.is_sqlite:
            cur.execute("SELECT attempts FROM jobs WHERE job_id=?", (job_id,))
            row = cur.fetchone()
            attempts = (row[0] if row else 0) + 1
            status = "failed" if attempts >= max_attempts else "queued"
            next_run = (datetime.now(timezone.utc) + timedelta(seconds=2 ** attempts)).isoformat()
            cur.execute(
                "UPDATE jobs SET status=?, attempts=?, last_error=?, next_run_at=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (status, attempts, error, next_run, job_id),
            )
        else:
            cur.execute("SELECT attempts FROM jobs WHERE job_id=%s", (job_id,))
            row = cur.fetchone()
            attempts = (row[0] if row else 0) + 1
            status = "failed" if attempts >= max_attempts else "queued"
            next_run = datetime.now(timezone.utc) + timedelta(seconds=2 ** attempts)
            cur.execute(
                "UPDATE jobs SET status=%s, attempts=%s, last_error=%s, next_run_at=%s, updated_at=now() WHERE job_id=%s",
                (status, attempts, error, next_run, job_id),
            )
        conn.commit()
