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
            conn.commit()
        return

    schema_path = Path(__file__).with_name("schema.sql")
    sql = schema_path.read_text(encoding="utf-8")
    with get_conn(dsn) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()
