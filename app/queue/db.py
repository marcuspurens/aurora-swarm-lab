"""Database helpers for queue and manifest store."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from app.core.config import load_settings

try:
    import psycopg  # type: ignore
except Exception:
    psycopg = None

try:
    import psycopg2  # type: ignore
except Exception:
    psycopg2 = None


@dataclass
class ConnWrapper:
    conn: object
    is_sqlite: bool

    def cursor(self):
        return self.conn.cursor()

    def commit(self):
        return self.conn.commit()

    def close(self):
        return self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def _sqlite_conn(dsn: str) -> ConnWrapper:
    path = dsn.replace("sqlite://", "", 1)
    # Keep absolute paths (e.g. /tmp/queue.db) but treat "/./..." and "/../..."
    # as relative path hints used by configs like sqlite:///./data/aurora_queue.db.
    if path.startswith("/./") or path == "/.":
        path = path[1:]
    elif path.startswith("/../") or path == "/..":
        path = path[1:]
    if path == "" or path == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return ConnWrapper(conn=conn, is_sqlite=True)


def _postgres_conn(dsn: str) -> ConnWrapper:
    if psycopg is not None:
        conn = psycopg.connect(dsn)
        return ConnWrapper(conn=conn, is_sqlite=False)
    if psycopg2 is not None:
        conn = psycopg2.connect(dsn)
        return ConnWrapper(conn=conn, is_sqlite=False)
    raise RuntimeError("Postgres driver not available. Install psycopg or psycopg2.")


@contextmanager
def get_conn(dsn: Optional[str] = None) -> Iterator[ConnWrapper]:
    settings = load_settings()
    dsn = dsn or settings.postgres_dsn
    if dsn.startswith("sqlite://"):
        conn = _sqlite_conn(dsn)
    else:
        conn = _postgres_conn(dsn)
    try:
        yield conn
    finally:
        conn.close()


def init_db(dsn: Optional[str] = None) -> None:
    settings = load_settings()
    dsn = dsn or settings.postgres_dsn

    if dsn.startswith("sqlite://"):
        with get_conn(dsn) as conn:
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS manifests (source_id TEXT, source_version TEXT, manifest_json TEXT, updated_at TEXT, PRIMARY KEY (source_id, source_version))"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, job_type TEXT, lane TEXT, status TEXT, source_id TEXT, source_version TEXT, attempts INT, next_run_at TEXT, locked_until TEXT, last_error TEXT, created_at TEXT, updated_at TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS run_log (run_id TEXT PRIMARY KEY, created_at TEXT, lane TEXT, component TEXT, model TEXT, input_json TEXT, output_json TEXT, error TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS memory_items ("
                "memory_id TEXT PRIMARY KEY, memory_type TEXT, text TEXT, topics TEXT, entities TEXT, source_refs TEXT, "
                "importance REAL NOT NULL DEFAULT 0.5, confidence REAL NOT NULL DEFAULT 0.7, "
                "access_count INTEGER NOT NULL DEFAULT 0, last_accessed_at TEXT, expires_at TEXT, pinned_until TEXT, "
                "created_at TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS embeddings (doc_id TEXT, segment_id TEXT, source_id TEXT, source_version TEXT, text TEXT, text_hash TEXT, embedding TEXT, start_ms INTEGER, end_ms INTEGER, speaker TEXT, source_refs TEXT, updated_at TEXT, PRIMARY KEY (doc_id, segment_id))"
            )
            conn.commit()
            _ensure_memory_columns(conn)
        return

    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    with get_conn(dsn) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
        _ensure_memory_columns(conn)


def _ensure_memory_columns(conn: ConnWrapper) -> None:
    cur = conn.cursor()
    if conn.is_sqlite:
        cur.execute("PRAGMA table_info(memory_items)")
        rows = cur.fetchall()
        existing = {str(row[1]).lower() for row in rows}
        stmts = []
        if "importance" not in existing:
            stmts.append("ALTER TABLE memory_items ADD COLUMN importance REAL NOT NULL DEFAULT 0.5")
        if "confidence" not in existing:
            stmts.append("ALTER TABLE memory_items ADD COLUMN confidence REAL NOT NULL DEFAULT 0.7")
        if "access_count" not in existing:
            stmts.append("ALTER TABLE memory_items ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0")
        if "last_accessed_at" not in existing:
            stmts.append("ALTER TABLE memory_items ADD COLUMN last_accessed_at TEXT")
        if "expires_at" not in existing:
            stmts.append("ALTER TABLE memory_items ADD COLUMN expires_at TEXT")
        if "pinned_until" not in existing:
            stmts.append("ALTER TABLE memory_items ADD COLUMN pinned_until TEXT")
        for stmt in stmts:
            try:
                cur.execute(stmt)
            except Exception:
                pass
        conn.commit()
        return

    try:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'memory_items'"
        )
        rows = cur.fetchall()
        existing = {str(row[0]).lower() for row in rows}
    except Exception:
        return

    stmts = []
    if "importance" not in existing:
        stmts.append("ALTER TABLE memory_items ADD COLUMN importance DOUBLE PRECISION NOT NULL DEFAULT 0.5")
    if "confidence" not in existing:
        stmts.append("ALTER TABLE memory_items ADD COLUMN confidence DOUBLE PRECISION NOT NULL DEFAULT 0.7")
    if "access_count" not in existing:
        stmts.append("ALTER TABLE memory_items ADD COLUMN access_count INT NOT NULL DEFAULT 0")
    if "last_accessed_at" not in existing:
        stmts.append("ALTER TABLE memory_items ADD COLUMN last_accessed_at TIMESTAMPTZ")
    if "expires_at" not in existing:
        stmts.append("ALTER TABLE memory_items ADD COLUMN expires_at TIMESTAMPTZ")
    if "pinned_until" not in existing:
        stmts.append("ALTER TABLE memory_items ADD COLUMN pinned_until TIMESTAMPTZ")
    for stmt in stmts:
        try:
            cur.execute(stmt)
        except Exception:
            pass
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_type_created ON memory_items(memory_type, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_expires ON memory_items(expires_at)")
    except Exception:
        pass
    conn.commit()
