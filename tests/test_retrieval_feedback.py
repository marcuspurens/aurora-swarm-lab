from app.modules.memory.memory_recall import recall
from app.modules.memory.retrieval_feedback import (
    apply_retrieval_feedback,
    record_retrieval_feedback,
)
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
