from app.queue.db import init_db
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
