from app.modules.retrieve.retrieve_snowflake import retrieve
from app.modules.memory.context_handoff import record_turn_and_refresh
from app.modules.memory.memory_write import write_memory
from app.queue.db import init_db


class FakeClient:
    def search_segments(self, query: str, limit: int = 10, filters=None) -> str:
        return f"SQL({query},{limit},{filters})"

    def execute_query(self, sql: str):
        return [
            {
                "doc_id": "d1",
                "segment_id": "s1",
                "start_ms": 0,
                "end_ms": 10,
                "speaker": "UNKNOWN",
                "text": "hello",
            }
        ]


class FakeEmptyClient:
    def search_segments(self, query: str, limit: int = 10, filters=None) -> str:
        return f"SQL({query},{limit},{filters})"

    def execute_query(self, sql: str):
        return []


class FakeDualClient:
    def search_segments(self, query: str, limit: int = 10, filters=None) -> str:
        return f"SQL({query},{limit},{filters})"

    def execute_query(self, sql: str):
        return [
            {
                "doc_id": "doc-a",
                "segment_id": "seg-a",
                "start_ms": 0,
                "end_ms": 10,
                "speaker": "UNKNOWN",
                "text": "aurora roadmap timeline",
            },
            {
                "doc_id": "doc-b",
                "segment_id": "seg-b",
                "start_ms": 0,
                "end_ms": 10,
                "speaker": "UNKNOWN",
                "text": "aurora roadmap timeline",
            },
        ]


def test_retrieve_shape(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("MEMORY_RETRIEVE_LIMIT", "3")
    init_db()
    write_memory(memory_type="working", text="hello from memory", publish_long_term=False)

    results = retrieve("hello", limit=5, filters={"topics": ["a"]}, client=FakeClient())
    assert isinstance(results, list)
    assert any(r.get("doc_id") == "d1" for r in results)
    assert any(str(r.get("doc_id", "")).startswith("memory:") for r in results)


def test_retrieve_uses_context_handoff(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("MEMORY_ENABLED", "0")
    monkeypatch.setenv("CONTEXT_HANDOFF_ENABLED", "1")
    init_db()
    record_turn_and_refresh(
        question="What are we working on?",
        answer_text="We are implementing automatic context handoff.",
        citations=[],
    )

    results = retrieve("status what are we working on next", limit=5, client=FakeEmptyClient())
    assert any(r.get("doc_id") == "context:auto_handoff" for r in results)


def test_retrieve_filters_memory_by_kind(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("CONTEXT_HANDOFF_ENABLED", "0")
    monkeypatch.setenv("MEMORY_RETRIEVE_LIMIT", "8")
    init_db()

    write_memory(
        memory_type="working",
        memory_kind="procedural",
        text="runbook for deployment to prod",
        publish_long_term=False,
    )
    write_memory(
        memory_type="working",
        memory_kind="semantic",
        text="fact about deployment constraints",
        publish_long_term=False,
    )

    results = retrieve(
        "deployment",
        limit=6,
        filters={"memory_kind": "procedural"},
        client=FakeEmptyClient(),
    )
    memory_rows = [row for row in results if str(row.get("doc_id", "")).startswith("memory:")]
    assert memory_rows
    assert all(row.get("memory_kind") == "procedural" for row in memory_rows)


def test_retrieve_uses_feedback_to_rerank_segments(tmp_path, monkeypatch):
    from app.modules.memory.retrieval_feedback import record_retrieval_feedback

    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "0")
    monkeypatch.setenv("MEMORY_ENABLED", "1")
    monkeypatch.setenv("CONTEXT_HANDOFF_ENABLED", "0")
    monkeypatch.setenv("RETRIEVAL_FEEDBACK_ENABLED", "1")
    init_db()

    record_retrieval_feedback(
        question="aurora roadmap timeline",
        evidence=[
            {"doc_id": "doc-a", "segment_id": "seg-a", "retrieval_source": "keyword"},
            {"doc_id": "doc-b", "segment_id": "seg-b", "retrieval_source": "keyword"},
        ],
        citations=[{"doc_id": "doc-a", "segment_id": "seg-a"}],
        answer_text="answer used doc-a",
    )

    results = retrieve("aurora roadmap timeline", limit=3, client=FakeDualClient())
    top_two = [row for row in results if row.get("doc_id") in {"doc-a", "doc-b"}][:2]
    assert len(top_two) == 2
    assert top_two[0]["doc_id"] == "doc-a"
