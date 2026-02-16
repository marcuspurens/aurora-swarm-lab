import json
from pathlib import Path

from app.queue.db import init_db
from app.queue.db import get_conn
from app.queue.jobs import enqueue_job, claim_job, mark_done
from app.queue.logs import log_run


def test_queue_enqueue_claim_done(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    job_id = enqueue_job("ingest_url", "io", "url:https://example.com", "v1")
    job = claim_job("io")
    assert job is not None
    assert job["job_id"] == job_id
    mark_done(job_id)


def test_sqlite_relative_dot_path_stays_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POSTGRES_DSN", "sqlite:///./data/aurora_queue.db")
    init_db()
    assert Path("data/aurora_queue.db").exists()


def test_run_log_payload_is_capped(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("RUN_LOG_MAX_JSON_CHARS", "320")
    monkeypatch.setenv("RUN_LOG_MAX_ERROR_CHARS", "240")
    init_db()

    log_run(
        lane="io",
        component="test_component",
        input_json={"huge": "x" * 4000},
        output_json={"huge": "y" * 4000},
        error="z" * 1000,
    )

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT input_json, output_json, error FROM run_log LIMIT 1")
        row = cur.fetchone()

    input_json = str(row[0] or "")
    output_json = str(row[1] or "")
    error = str(row[2] or "")

    assert len(input_json) <= 320
    assert len(output_json) <= 320
    assert len(error) <= 240
    assert json.loads(input_json).get("truncated") is True
    assert json.loads(output_json).get("truncated") is True
    assert error.endswith("...<truncated>")
