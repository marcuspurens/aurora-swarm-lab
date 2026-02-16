import json

from app.modules.voiceprint import diarize, enroll, match, review
from app.queue.db import init_db
from app.core.storage import write_artifact, read_artifact
from app.core.manifest import upsert_manifest, get_manifest


def test_voiceprint_pipeline(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:abc"
    source_version = "v1"
    segments = [
        {"doc_id": source_id, "segment_id": "seg_1", "start_ms": 0, "end_ms": 1000, "speaker_local_id": "UNKNOWN", "text": "Hello"}
    ]
    lines = "\n".join(json.dumps(s, ensure_ascii=True) for s in segments)
    write_artifact(source_id, source_version, "transcript/segments.jsonl", lines)
    write_artifact(source_id, source_version, "audio/source.m4a", "dummy")
    upsert_manifest(
        source_id,
        source_version,
        {
            "source_id": source_id,
            "source_version": source_version,
            "artifacts": {"segments": "transcript/segments.jsonl", "audio": "audio/source.m4a"},
        },
    )

    diarize.handle_job({"source_id": source_id, "source_version": source_version, "lane": "transcribe"})
    assert read_artifact(source_id, source_version, "transcript/segments_diarized.jsonl") is not None

    enroll.handle_job({"source_id": source_id, "source_version": source_version, "lane": "nemotron"})
    assert read_artifact(source_id, source_version, "voiceprint/voiceprints.jsonl") is not None

    match.handle_job({"source_id": source_id, "source_version": source_version, "lane": "nemotron"})
    assert read_artifact(source_id, source_version, "voiceprint/matches.jsonl") is not None

    review.handle_job({"source_id": source_id, "source_version": source_version, "lane": "nemotron"})
    assert read_artifact(source_id, source_version, "voiceprint/review.json") is not None

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("steps", {}).get("voiceprint_review", {}).get("status") == "done"
