from app.modules.memory.memory_recall import recall
from app.modules.memory.retrieval_feedback import (
    apply_retrieval_feedback,
    record_retrieval_feedback,
)
from app.queue.db import get_conn
from app.queue.db import init_db


def test_record_retrieval_feedback_writes_memory(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    init_db()

    receipt = record_retrieval_feedback(
        question="What is Aurora roadmap status?",
        evidence=[
            {"doc_id": "d1", "segment_id": "s1", "retrieval_source": "keyword"},
            {"doc_id": "d2", "segment_id": "s2", "retrieval_source": "memory"},
        ],
        citations=[{"doc_id": "d1", "segment_id": "s1"}],
        answer_text="Roadmap is active.",
    )
    assert receipt is not None
    assert int(receipt.get("signals") or 0) >= 1

    rows = recall("Retrieval feedback for question", limit=5, memory_type="working")
    assert rows
    refs = rows[0].get("source_refs") or {}
    assert refs.get("kind") == "retrieval_feedback"


def test_apply_retrieval_feedback_boosts_cited_and_penalizes_missed(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    init_db()

    record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[
            {"doc_id": "doc-good", "segment_id": "seg-1", "retrieval_source": "keyword"},
            {"doc_id": "doc-missed", "segment_id": "seg-2", "retrieval_source": "keyword"},
        ],
        citations=[{"doc_id": "doc-good", "segment_id": "seg-1"}],
        answer_text="Based on doc-good.",
    )

    rows = [
        {"doc_id": "doc-good", "segment_id": "seg-1", "final_score": 0.5, "score": 0.5},
        {"doc_id": "doc-missed", "segment_id": "seg-2", "final_score": 0.5, "score": 0.5},
    ]
    apply_retrieval_feedback("aurora roadmap next steps", rows)
    assert rows[0]["final_score"] > rows[1]["final_score"]
    assert float(rows[0].get("feedback_boost") or 0.0) > 0.0


def test_apply_retrieval_feedback_respects_scope(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    init_db()

    record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-good", "segment_id": "seg-1", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-good", "segment_id": "seg-1"}],
        answer_text="Based on doc-good.",
        user_id="alice",
        project_id="aurora",
        session_id="sess-1",
    )

    rows = [{"doc_id": "doc-good", "segment_id": "seg-1", "final_score": 0.5, "score": 0.5}]
    apply_retrieval_feedback(
        "aurora roadmap next steps",
        rows,
        user_id="bob",
        project_id="other",
        session_id="sess-2",
    )
    assert rows[0]["final_score"] == 0.5
    assert "feedback_boost" not in rows[0]


def test_apply_retrieval_feedback_applies_time_decay(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_DECAY_HALF_LIFE_HOURS", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_CITED_BOOST", "0.1")
    init_db()

    old_receipt = record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-old", "segment_id": "seg-1", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-old", "segment_id": "seg-1"}],
        answer_text="old",
    )
    fresh_receipt = record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-fresh", "segment_id": "seg-2", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-fresh", "segment_id": "seg-2"}],
        answer_text="fresh",
    )
    assert old_receipt and fresh_receipt

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE memory_items SET created_at=? WHERE memory_id=?",
            ("2000-01-01T00:00:00+00:00", str(old_receipt["memory_id"])),
        )
        conn.commit()

    rows = [
        {"doc_id": "doc-old", "segment_id": "seg-1", "final_score": 0.5, "score": 0.5},
        {"doc_id": "doc-fresh", "segment_id": "seg-2", "final_score": 0.5, "score": 0.5},
    ]
    apply_retrieval_feedback("aurora roadmap timeline", rows)
    old_boost = float(rows[0].get("feedback_boost") or 0.0)
    fresh_boost = float(rows[1].get("feedback_boost") or 0.0)
    assert fresh_boost > 0.0
    assert fresh_boost > old_boost


def test_apply_retrieval_feedback_caps_per_query_cluster(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_CLUSTER_CAP", "1")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_CITED_BOOST", "0.1")
    init_db()

    record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-good", "segment_id": "seg-1", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-good", "segment_id": "seg-1"}],
        answer_text="first",
    )
    record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[{"doc_id": "doc-good", "segment_id": "seg-1", "retrieval_source": "keyword"}],
        citations=[{"doc_id": "doc-good", "segment_id": "seg-1"}],
        answer_text="second",
    )

    rows = [{"doc_id": "doc-good", "segment_id": "seg-1", "final_score": 0.5, "score": 0.5}]
    apply_retrieval_feedback("aurora roadmap timeline", rows)
    boost = float(rows[0].get("feedback_boost") or 0.0)
    assert boost > 0.10
    assert boost < 0.20
