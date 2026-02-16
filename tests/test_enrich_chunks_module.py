import json

from app.core.manifest import upsert_manifest, get_manifest
from app.core.storage import write_artifact, read_artifact
from app.queue.db import init_db
from app.modules.enrich import enrich_chunks
from app.core.models import ChunkEnrichOutput


def test_enrich_chunks_handle_job(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v1"
    chunks = [
        {"doc_id": source_id, "segment_id": "chunk_1", "text": "Hello", "source_refs": {"chunk_index": 1}},
    ]
    lines = "\n".join(json.dumps(c, ensure_ascii=True) for c in chunks)
    write_artifact(source_id, source_version, "chunks/chunks.jsonl", lines)
    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"chunks": "chunks/chunks.jsonl"}},
    )

    def fake_enrich(text):
        return ChunkEnrichOutput(topics=["t"], entities=["e"])

    monkeypatch.setattr(enrich_chunks, "enrich_chunk", fake_enrich)
    enqueued = []
    monkeypatch.setattr(enrich_chunks, "enqueue_job", lambda *args, **kwargs: enqueued.append(args))

    enrich_chunks.handle_job({"source_id": source_id, "source_version": source_version})

    payload = read_artifact(source_id, source_version, "enrich/chunks.jsonl")
    assert payload is not None
    data = json.loads(payload.splitlines()[0])
    assert data["topics"] == ["t"]

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("steps", {}).get("enrich_chunks", {}).get("status") == "done"
    assert len(enqueued) == 3
