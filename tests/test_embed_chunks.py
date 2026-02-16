import json

from app.core.manifest import upsert_manifest
from app.core.storage import write_artifact
from app.modules.embeddings import embed_chunks
from app.queue.db import get_conn, init_db


def test_embed_chunks_job(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "1")
    init_db()

    source_id = "doc:test"
    source_version = "v1"
    upsert_manifest(
        source_id,
        source_version,
        {"artifacts": {"chunks": "chunks/chunks.jsonl"}, "steps": {}, "source_id": source_id},
    )

    chunks = [
        {"doc_id": source_id, "segment_id": "chunk_1", "text": "hello world", "source_refs": {}},
    ]
    write_artifact(source_id, source_version, "chunks/chunks.jsonl", "\n".join(json.dumps(c) for c in chunks))

    monkeypatch.setattr(embed_chunks, "embed", lambda text: [0.5, 0.5])
    embed_chunks.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM embeddings")
        count = cur.fetchone()[0]
    assert count == 1
