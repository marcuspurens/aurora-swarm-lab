from app.core.manifest import upsert_manifest, get_manifest
from app.core.storage import write_artifact, artifact_path
from app.queue.db import init_db
from app.modules.chunk import chunk_text


def test_chunk_text_handle_job_writes_chunks(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v1"
    write_artifact(source_id, source_version, "text/canonical.txt", "one two three four five")
    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"canonical_text": "text/canonical.txt"}},
    )

    enqueued = []
    monkeypatch.setattr(chunk_text, "enqueue_job", lambda *args, **kwargs: enqueued.append(args))

    chunk_text.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    chunks_path = artifact_path(source_id, source_version, "chunks/chunks.jsonl")
    assert chunks_path.exists()

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("steps", {}).get("chunk_text", {}).get("status") == "done"
    assert len(enqueued) == 3
    job_types = [args[0] for args in enqueued]
    assert "embed_chunks" in job_types
    assert "enrich_doc" in job_types
    assert "enrich_chunks" in job_types


def test_chunk_text_includes_intake_annotations_in_source_refs(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "url:https://example.com"
    source_version = "v2"
    write_artifact(source_id, source_version, "text/canonical.txt", "one two three four five")
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "metadata": {
                "intake": {
                    "tags": ["policy", "ai"],
                    "context": "Context " * 100,
                    "source_metadata": {
                        "speaker": "Philipp Roth",
                        "organization": "ORF",
                        "event_date": "2025-06-24",
                    },
                }
            },
            "artifacts": {"canonical_text": "text/canonical.txt"},
        },
    )

    monkeypatch.setattr(chunk_text, "enqueue_job", lambda *args, **kwargs: None)
    chunk_text.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    chunks_path = artifact_path(source_id, source_version, "chunks/chunks.jsonl")
    data = chunks_path.read_text(encoding="utf-8").strip().splitlines()
    first = data[0]
    assert '"intake_tags": ["policy", "ai"]' in first
    assert '"intake_context":' in first
    assert '"intake_speaker": "Philipp Roth"' in first
    assert '"intake_organization": "ORF"' in first
    assert '"intake_event_date": "2025-06-24"' in first
