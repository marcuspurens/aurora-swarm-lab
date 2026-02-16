from app.queue.db import init_db
from app.queue.db import get_conn
from app.modules.memory import memory_write, memory_recall


def test_memory_write_and_recall(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    receipt = memory_write.write_memory(
        memory_type="working",
        text="Remember this",
        topics=["todo"],
        entities=["Aurora"],
        source_refs={"note": "x"},
        publish_long_term=False,
    )
    assert receipt["memory_id"]

    results = memory_recall.recall("Remember", limit=5, memory_type="working")
    assert len(results) == 1
    assert results[0]["text"] == "Remember this"
    assert "recall_score" in results[0]
    assert results[0]["memory_type"] == "working"


def test_memory_recall_ranking_and_expiry(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    memory_write.write_memory(
        memory_type="working",
        text="Project Aurora launch checklist",
        topics=["launch"],
        importance=0.9,
        confidence=0.9,
        publish_long_term=False,
    )
    memory_write.write_memory(
        memory_type="working",
        text="Temporary note",
        topics=["launch"],
        importance=1.0,
        confidence=1.0,
        expires_at="2000-01-01T00:00:00+00:00",
        publish_long_term=False,
    )

    results = memory_recall.recall("Aurora launch", limit=5, memory_type="working")
    assert len(results) == 1
    assert results[0]["text"] == "Project Aurora launch checklist"


def test_memory_write_supersedes_conflicting_slot(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    first = memory_write.write_memory(
        memory_type="working",
        text="My favorite editor is vim",
        publish_long_term=False,
        overwrite_conflicts=True,
    )
    second = memory_write.write_memory(
        memory_type="working",
        text="My favorite editor is helix",
        publish_long_term=False,
        overwrite_conflicts=True,
    )

    assert second["superseded_count"] >= 1

    results = memory_recall.recall("favorite editor", limit=10, memory_type="working")
    ids = {item["memory_id"] for item in results}
    assert second["memory_id"] in ids
    assert first["memory_id"] not in ids


def test_memory_write_records_revision_trail_on_supersede(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    first = memory_write.write_memory(
        memory_type="working",
        text="My favorite editor is vim",
        publish_long_term=False,
        overwrite_conflicts=True,
    )
    second = memory_write.write_memory(
        memory_type="working",
        text="My favorite editor is helix",
        publish_long_term=False,
        overwrite_conflicts=True,
    )

    assert second["superseded_count"] >= 1
    assert first["memory_id"] in (second.get("superseded_ids") or [])

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT source_refs FROM memory_items WHERE memory_id=?", (first["memory_id"],))
        first_row = cur.fetchone()
        cur.execute("SELECT source_refs FROM memory_items WHERE memory_id=?", (second["memory_id"],))
        second_row = cur.fetchone()

    first_refs = memory_write._json_loads(first_row[0]) or {}
    second_refs = memory_write._json_loads(second_row[0]) or {}
    assert first_refs.get("superseded_by") == second["memory_id"]
    assert first_refs.get("supersede_reason_code") == "slot_value_conflict"
    first_timeline = first_refs.get("revision_timeline") or []
    assert any(event.get("event") == "superseded" for event in first_timeline if isinstance(event, dict))
    assert second_refs.get("supersedes")
    assert first["memory_id"] in second_refs.get("supersedes")
    second_timeline = second_refs.get("revision_timeline") or []
    assert any(event.get("event") == "supersedes" for event in second_timeline if isinstance(event, dict))


def test_memory_recall_filters_by_memory_kind(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    memory_write.write_memory(
        memory_type="working",
        memory_kind="procedural",
        text="How to run migration safely",
        publish_long_term=False,
    )
    memory_write.write_memory(
        memory_type="working",
        memory_kind="semantic",
        text="Migration policy and constraints",
        publish_long_term=False,
    )

    results = memory_recall.recall("migration", limit=10, memory_type="working", memory_kind="procedural")
    assert results
    assert all(item.get("memory_kind") == "procedural" for item in results)


def test_memory_recall_filters_by_scope(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    scoped = memory_write.write_memory(
        memory_type="working",
        text="Scoped memory for project alpha",
        publish_long_term=False,
        user_id="user-a",
        project_id="project-alpha",
        session_id="session-1",
    )
    memory_write.write_memory(
        memory_type="working",
        text="Other tenant memory",
        publish_long_term=False,
        user_id="user-b",
        project_id="project-beta",
        session_id="session-2",
    )

    scoped_results = memory_recall.recall(
        "memory",
        limit=10,
        memory_type="working",
        user_id="user-a",
        project_id="project-alpha",
        session_id="session-1",
    )
    assert len(scoped_results) == 1
    assert scoped_results[0]["memory_id"] == scoped["memory_id"]
