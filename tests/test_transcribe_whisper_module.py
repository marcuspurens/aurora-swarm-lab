from pathlib import Path

from app.core.manifest import upsert_manifest, get_manifest
from app.core.storage import artifact_path
from app.queue.db import init_db
from app.modules.transcribe import transcribe_whisper_cli


def test_transcribe_handle_job_writes_segments(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:abc123"
    source_version = "v1"
    audio_rel = "audio/source.m4a"
    audio_path = artifact_path(source_id, source_version, audio_rel)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio")

    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"audio": audio_rel}},
    )

    def fake_run_whisper_backend(audio_path_arg: str, output_dir: str, output_format: str = "srt"):
        out = Path(output_dir) / "source.srt"
        out.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello world\n\n",
            encoding="utf-8",
        )
        return out, "whisper_cli"

    monkeypatch.setattr(transcribe_whisper_cli, "run_whisper_backend", fake_run_whisper_backend)

    transcribe_whisper_cli.handle_job(
        {"source_id": source_id, "source_version": source_version, "lane": "transcribe"}
    )

    segments_path = artifact_path(source_id, source_version, "transcript/segments.jsonl")
    assert segments_path.exists()

    manifest = get_manifest(source_id, source_version)
    assert manifest is not None
    assert manifest.get("steps", {}).get("transcribe_whisper", {}).get("status") == "done"
    assert manifest.get("steps", {}).get("transcribe_whisper", {}).get("backend") == "whisper_cli"
