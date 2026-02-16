from app.modules.memory.memory_stats import get_memory_stats
from app.modules.memory.memory_write import write_memory
from app.modules.memory.retrieval_feedback import record_retrieval_feedback
from app.queue.db import init_db


def test_memory_stats_reports_supersede_and_feedback_metrics(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    init_db()

    first = write_memory(
        memory_type="working",
        text="My favorite editor is vim",
        publish_long_term=False,
        overwrite_conflicts=True,
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    second = write_memory(
        memory_type="working",
        text="My favorite editor is helix",
        publish_long_term=False,
        overwrite_conflicts=True,
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    assert first["memory_id"]
    assert second["memory_id"]

    receipt = record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[
            {"doc_id": "doc-good", "segment_id": "seg-1", "retrieval_source": "keyword"},
            {"doc_id": "doc-missed", "segment_id": "seg-2", "retrieval_source": "keyword"},
        ],
        citations=[{"doc_id": "doc-good", "segment_id": "seg-1"}],
        answer_text="based on cited doc",
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    assert receipt

    stats = get_memory_stats(user_id="user-a", project_id="proj-a", session_id="sess-a")
    assert stats["totals"]["memory_items"] == 3
    assert stats["by_memory_type"]["working"] == 3
    assert stats["supersede"]["superseded_items"] == 1
    assert stats["supersede"]["supersede_actions"] == 1
    assert stats["supersede"]["supersede_link_count"] >= 1
    assert stats["supersede"]["supersede_rate"] == round(1.0 / 3.0, 6)
    assert stats["retrieval_feedback"]["feedback_items"] == 1
    assert stats["retrieval_feedback"]["signals_total"] == 2
    assert stats["retrieval_feedback"]["cited_signals"] == 1
    assert stats["retrieval_feedback"]["missed_signals"] == 1
    assert stats["retrieval_feedback"]["hit_rate"] == 0.5


def test_memory_stats_respects_scope(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    init_db()

    write_memory(
        memory_type="working",
        text="scope a memory",
        publish_long_term=False,
        user_id="user-a",
        project_id="proj-a",
        session_id="sess-a",
    )
    write_memory(
        memory_type="working",
        text="scope b memory",
        publish_long_term=False,
        user_id="user-b",
        project_id="proj-b",
        session_id="sess-b",
    )

    stats_a = get_memory_stats(user_id="user-a", project_id="proj-a", session_id="sess-a")
    stats_b = get_memory_stats(user_id="user-b", project_id="proj-b", session_id="sess-b")
    assert stats_a["totals"]["memory_items"] == 1
    assert stats_b["totals"]["memory_items"] == 1
