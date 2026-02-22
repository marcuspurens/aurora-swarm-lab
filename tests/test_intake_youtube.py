from pathlib import Path

from app.core.ids import sha256_bytes
from app.core.manifest import get_manifest
from app.core.storage import artifact_path
from app.queue.db import init_db
from app.queue.jobs import claim_job
from app.modules.intake import intake_youtube


def test_ingest_youtube_writes_audio_and_enqueues_transcribe(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    def fake_info(url: str):
        return {"id": "abc123", "title": "Demo", "uploader": "Channel"}

    def fake_extract(url: str, output_path: str):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = b"audio-bytes"
        out.write_bytes(data)
        return out

    monkeypatch.setattr(intake_youtube, "get_video_info", fake_info)
    monkeypatch.setattr(intake_youtube, "extract_audio", fake_extract)

    source_id = "youtube:abc123"
    source_version = sha256_bytes(b"audio-bytes")
    _ = intake_youtube.ingest_youtube("abc123", source_id, source_version)

    stored = get_manifest(source_id, source_version)
    assert stored is not None
    audio = artifact_path(source_id, source_version, "audio/source.m4a")
    assert audio.exists()

    job = claim_job("transcribe")
    assert job is not None
    assert job["job_type"] == "denoise_audio"
