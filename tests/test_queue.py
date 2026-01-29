from app.queue.db import init_db
from app.queue.jobs import enqueue_job, claim_job, mark_done


def test_queue_enqueue_claim_done(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    job_id = enqueue_job("ingest_url", "io", "url:https://example.com", "v1")
    job = claim_job("io")
    assert job is not None
    assert job["job_id"] == job_id
    mark_done(job_id)
