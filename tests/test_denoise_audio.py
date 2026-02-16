from app.modules.audio import denoise_audio
from app.queue.db import init_db
from app.core.storage import write_artifact, read_artifact
from app.core.manifest import upsert_manifest, get_manifest


def test_denoise_audio_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "queue.db"
    artifacts_root = tmp_path / "artifacts"
    monkeypatch.setenv("POSTGRES_DSN", f"sqlite://{db_path}")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifacts_root))
    init_db()

    source_id = "youtube:abc"
    source_version = "v1"
    write_artifact(source_id, source_version, "audio/source.m4a", "raw")
    upsert_manifest(
        source_id,
        source_version,
        {"source_id": source_id, "source_version": source_version, "artifacts": {"audio": "audio/source.m4a"}},
    )

    def fake_denoise(input_path, output_path):
        raise RuntimeError("no backend")

    monkeypatch.setattr(denoise_audio, "denoise_audio", fake_denoise)

    denoise_audio.handle_job({"source_id": source_id, "source_version": source_version, "lane": "transcribe"})

    out = read_artifact(source_id, source_version, "audio/denoised.wav")
    assert out is not None

    manifest = get_manifest(source_id, source_version)
    assert manifest.get("artifacts", {}).get("audio_denoised") == "audio/denoised.wav"
