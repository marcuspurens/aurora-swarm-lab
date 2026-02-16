from pathlib import Path
from datetime import timedelta

from app.modules.memory.context_handoff import (
    get_handoff,
    inject_session_resume_evidence,
    load_handoff_text,
    record_turn_and_refresh,
    reset_session_resume_tracking,
)
from app.modules.memory.memory_recall import recall
from app.queue.db import init_db


def test_context_handoff_record_and_load(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("CONTEXT_HANDOFF_TURN_LIMIT", "10")
    init_db()

    payload = record_turn_and_refresh(
        question="What is next for Aurora memory?",
        answer_text="Next we add autonomous context handoff and verify with tests.",
        citations=[{"doc_id": "d1", "segment_id": "s1"}],
    )
    path = Path(str(payload["path"]))
    assert path.exists()

    text = load_handoff_text()
    assert text is not None
    assert "Aurora Auto Handoff" in text
    assert "What is next for Aurora memory?" in text
    assert "d1:s1" in text

    latest = get_handoff()
    assert latest["text"] == text


def test_context_handoff_injects_once_per_session(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("CONTEXT_HANDOFF_RESUME_IDLE_MINUTES", "60")
    init_db()
    reset_session_resume_tracking()

    record_turn_and_refresh(
        question="What is next?",
        answer_text="Next step is to implement session resume injection.",
        citations=[],
    )

    evidence = [{"doc_id": "d1", "segment_id": "s1", "text_snippet": "local evidence"}]
    injected = inject_session_resume_evidence(evidence, session_id="chat-a")
    assert injected is True
    assert any(item.get("doc_id") == "context:auto_handoff" for item in evidence)

    evidence_second = [{"doc_id": "d2", "segment_id": "s2", "text_snippet": "another"}]
    injected_second = inject_session_resume_evidence(evidence_second, session_id="chat-a")
    assert injected_second is False
    assert not any(item.get("doc_id") == "context:auto_handoff" for item in evidence_second)

    evidence_new_session = [{"doc_id": "d3", "segment_id": "s3", "text_snippet": "third"}]
    injected_new_session = inject_session_resume_evidence(evidence_new_session, session_id="chat-b")
    assert injected_new_session is True
    assert any(item.get("doc_id") == "context:auto_handoff" for item in evidence_new_session)


def test_context_handoff_reinjects_after_idle(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("CONTEXT_HANDOFF_RESUME_IDLE_MINUTES", "1")
    init_db()
    reset_session_resume_tracking()

    record_turn_and_refresh(
        question="Current status?",
        answer_text="Focus is context handoff stability.",
        citations=[],
    )

    evidence_first = []
    assert inject_session_resume_evidence(evidence_first, session_id="chat-idle") is True

    evidence_second = []
    assert inject_session_resume_evidence(evidence_second, session_id="chat-idle") is False

    from app.modules.memory import context_handoff as ch

    with ch._SESSION_LOCK:
        ch._SESSION_LAST_SEEN["chat-idle"] = ch.now_utc() - timedelta(minutes=2)

    evidence_third = []
    assert inject_session_resume_evidence(evidence_third, session_id="chat-idle") is True


def test_context_handoff_pre_compaction_trigger(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    monkeypatch.setenv("CONTEXT_HANDOFF_PRE_COMPACTION_TURN_COUNT", "2")
    init_db()

    record_turn_and_refresh(question="Q1", answer_text="A1", citations=[])
    record_turn_and_refresh(question="Q2", answer_text="A2", citations=[])

    compacted = recall("pre-compaction snapshot", limit=5, memory_type="working")
    assert compacted
    refs = compacted[0].get("source_refs") or {}
    assert refs.get("kind") == "session_pre_compaction"
    assert int(refs.get("turn_count")) == 2
