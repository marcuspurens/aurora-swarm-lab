import json

from app.core.manifest import upsert_manifest, get_manifest
from app.core.storage import write_artifact, artifact_path
from app.queue.db import init_db
from app.modules.chunk import chunk_transcript


def test_chunk_transcript_handle_job(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:abc123"
    source_version = "v1"
    segments = [
        {"doc_id": source_id, "segment_id": "seg_1", "start_ms": 0, "end_ms": 1000, "speaker_local_id": "UNKNOWN", "text": "Hello"},
        {"doc_id": source_id, "segment_id": "seg_2", "start_ms": 1000, "end_ms": 2000, "speaker_local_id": "UNKNOWN", "text": "world"},
    ]
    lines = "\n".join(json.dumps(s, ensure_ascii=True) for s in segments)
    write_artifact(source_id, source_version, "transcript/segments.jsonl", lines)
    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"segments": "transcript/segments.jsonl"}},
    )

    enqueued = []
    monkeypatch.setattr(chunk_transcript, "enqueue_job", lambda *args, **kwargs: enqueued.append(args))

    chunk_transcript.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    chunks_path = artifact_path(source_id, source_version, "chunks/chunks.jsonl")
    assert chunks_path.exists()

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("steps", {}).get("chunk_transcript", {}).get("status") == "done"
    assert len(enqueued) == 2
    job_types = [args[0] for args in enqueued]
    assert "embed_chunks" in job_types
    assert "enrich_chunks" in job_types


def test_chunk_transcript_includes_intake_annotations(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:xyz789"
    source_version = "v1"
    segments = [
        {"doc_id": source_id, "segment_id": "seg_1", "start_ms": 0, "end_ms": 1000, "speaker_local_id": "UNKNOWN", "text": "Hello"},
    ]
    lines = "\n".join(json.dumps(s, ensure_ascii=True) for s in segments)
    write_artifact(source_id, source_version, "transcript/segments.jsonl", lines)
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "metadata": {
                "intake": {
                    "tags": ["Knowledge Graph", "EBUCore+"],
                    "context": "From ontology to graph",
                    "source_metadata": {
                        "speaker": "Philipp Roth",
                        "organization": "ORF",
                        "event_date": "2025-06-24",
                    },
                }
            },
            "artifacts": {"segments": "transcript/segments.jsonl"},
        },
    )

    monkeypatch.setattr(chunk_transcript, "enqueue_job", lambda *args, **kwargs: None)
    chunk_transcript.handle_job({"source_id": source_id, "source_version": source_version, "lane": "oss20b"})

    chunks_path = artifact_path(source_id, source_version, "chunks/chunks.jsonl")
    first = chunks_path.read_text(encoding="utf-8").strip().splitlines()[0]
    assert '"intake_tags": ["Knowledge Graph", "EBUCore+"]' in first
    assert '"intake_context": "From ontology to graph"' in first
    assert '"intake_speaker": "Philipp Roth"' in first
    assert '"intake_organization": "ORF"' in first
    assert '"intake_event_date": "2025-06-24"' in first
