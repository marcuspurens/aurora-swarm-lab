"""Audio denoise step using DeepFilterNet (optional)."""

from __future__ import annotations

from typing import Dict

from app.clients.denoise_client import denoise_audio
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, write_artifact_bytes
from app.core.timeutil import utc_now
from app.queue.logs import log_run
from app.queue.jobs import enqueue_job


DENOISED_REL_PATH = "audio/denoised.wav"


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for denoise_audio")

    if artifact_path(source_id, source_version, DENOISED_REL_PATH).exists():
        return

    audio_rel = manifest.get("artifacts", {}).get("audio")
    if not audio_rel:
        raise RuntimeError("audio artifact not found")

    in_path = artifact_path(source_id, source_version, str(audio_rel))
    out_path = artifact_path(source_id, source_version, DENOISED_REL_PATH)

    run_id = log_run(
        lane=str(job.get("lane", "transcribe")),
        component="denoise_audio",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    try:
        denoise_audio(str(in_path), str(out_path))
    except Exception as exc:
        # fallback: passthrough copy
        data = in_path.read_bytes()
        write_artifact_bytes(source_id, source_version, DENOISED_REL_PATH, data)
        log_run(
            lane=str(job.get("lane", "transcribe")),
            component="denoise_audio",
            input_json={"run_id": run_id},
            error=str(exc),
        )
    else:
        log_run(
            lane=str(job.get("lane", "transcribe")),
            component="denoise_audio",
            input_json={"run_id": run_id},
            output_json={"denoised": DENOISED_REL_PATH},
        )

    manifest.setdefault("artifacts", {})["audio_denoised"] = DENOISED_REL_PATH
    manifest.setdefault("steps", {})["denoise_audio"] = {"status": "done"}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    enqueue_job("transcribe_whisper", "transcribe", source_id, source_version)
