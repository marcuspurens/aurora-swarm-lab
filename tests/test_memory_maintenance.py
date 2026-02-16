from app.modules.memory.maintenance import run_memory_maintenance
from app.modules.memory.memory_write import write_memory
from app.modules.memory.retrieval_feedback import record_retrieval_feedback
from app.queue.db import get_conn, init_db


def _count_memory_rows() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM memory_items")
        row = cur.fetchone()
    return int(row[0] if row else 0)


def test_memory_maintenance_prunes_expired_and_feedback(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("MEMORY_MAINTENANCE_FEEDBACK_RETENTION_DAYS", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_HISTORY_LIMIT", "1")
    init_db()

    keep = write_memory(
        memory_type="working",
        text="keep memory",
        publish_long_term=False,
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    write_memory(
        memory_type="working",
        text="expired memory",
        publish_long_term=False,
        expires_at="2000-01-01T00:00:00+00:00",
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    first_feedback = record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-old", "segment_id": "seg-1", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-old", "segment_id": "seg-1"}],
        answer_text="old",
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    second_feedback = record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-new", "segment_id": "seg-2", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-new", "segment_id": "seg-2"}],
        answer_text="new",
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    assert first_feedback and second_feedback

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE memory_items SET created_at=? WHERE memory_id=?",
            ("2000-01-01T00:00:00+00:00", str(first_feedback["memory_id"])),
        )
        conn.commit()

    before_count = _count_memory_rows()
    output = run_memory_maintenance(user_id="user-a", project_id="proj-a", session_id="sess-a")
    after_count = _count_memory_rows()

    assert before_count - after_count == int(output["deleted_total"])
    assert int(output["deleted_breakdown"]["expired"]) >= 1
    assert int(output["deleted_breakdown"]["feedback_retention"]) >= 1

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT memory_id FROM memory_items")
        ids = {str(row[0]) for row in cur.fetchall()}
    assert keep["memory_id"] in ids
    assert second_feedback["memory_id"] in ids
    assert first_feedback["memory_id"] not in ids


def test_memory_maintenance_respects_scope_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    init_db()

    scoped = write_memory(
        memory_type="working",
        text="expired in scope",
        publish_long_term=False,
        expires_at="2000-01-01T00:00:00+00:00",
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    other = write_memory(
        memory_type="working",
        text="expired in other scope",
        publish_long_term=False,
        expires_at="2000-01-01T00:00:00+00:00",
        user_id="user-b",
        project_id="proj-b",
        session_id="sess-b",
    )

    out = run_memory_maintenance(user_id="user-a", project_id="proj-a", session_id="sess-a")
    assert int(out["deleted_total"]) == 1

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT memory_id FROM memory_items")
        ids = {str(row[0]) for row in cur.fetchall()}
    assert scoped["memory_id"] not in ids
    assert other["memory_id"] in ids
