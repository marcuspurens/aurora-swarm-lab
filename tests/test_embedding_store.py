from app.modules.embeddings.embedding_store import search_embeddings, upsert_embedding
from app.queue.db import init_db


def test_embedding_search(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    init_db()

    upsert_embedding(
        {
            "doc_id": "doc1",
            "segment_id": "s1",
            "source_id": "doc1",
            "source_version": "v1",
            "text": "alpha",
            "text_hash": "h1",
            "embedding": [1.0, 0.0],
            "start_ms": None,
            "end_ms": None,
            "speaker": None,
            "source_refs": {},
        }
    )
    upsert_embedding(
        {
            "doc_id": "doc1",
            "segment_id": "s2",
            "source_id": "doc1",
            "source_version": "v1",
            "text": "beta",
            "text_hash": "h2",
            "embedding": [0.0, 1.0],
            "start_ms": None,
            "end_ms": None,
            "speaker": None,
            "source_refs": {},
        }
    )

    results = search_embeddings([1.0, 0.0], limit=1)
    assert results[0]["segment_id"] == "s1"
