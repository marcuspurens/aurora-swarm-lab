"""Transcribe audio via configured Whisper backend and parse segments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from app.clients.whisper_client import parse_srt_or_vtt, run_whisper_backend
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run


TRANSCRIPT_REL_PATH = "transcript/source.srt"
SEGMENTS_REL_PATH = "transcript/segments.jsonl"


def transcribe(audio_path: str, output_dir: str, doc_id: str, output_format: str = "srt") -> tuple[List[Dict[str, object]], str]:
    out_path, backend = run_whisper_backend(audio_path, output_dir, output_format=output_format)
    text = Path(out_path).read_text(encoding="utf-8")
    return parse_srt_or_vtt(text, doc_id=doc_id), backend


def transcribe_and_store(source_id: str, source_version: str, audio_rel_path: str) -> Dict[str, object]:
    output_dir = artifact_path(source_id, source_version, "transcript")
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_path = artifact_path(source_id, source_version, audio_rel_path)
    segments, backend = transcribe(str(audio_path), str(output_dir), doc_id=source_id)

    transcript_path = output_dir / "source.srt"
    if transcript_path.exists():
        content = transcript_path.read_text(encoding="utf-8")
        write_artifact(source_id, source_version, TRANSCRIPT_REL_PATH, content)

    lines = "\n".join(json.dumps(seg, ensure_ascii=True) for seg in segments)
    write_artifact(source_id, source_version, SEGMENTS_REL_PATH, lines)

    return {
        "transcript": TRANSCRIPT_REL_PATH,
        "segments": SEGMENTS_REL_PATH,
        "segment_count": len(segments),
        "backend": backend,
    }


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for transcription")

    audio_rel = manifest.get("artifacts", {}).get("audio_denoised") or manifest.get("artifacts", {}).get("audio")
    if not audio_rel:
        raise RuntimeError("Audio artifact not found in manifest")

    run_id = log_run(
        lane=str(job.get("lane", "transcribe")),
        component="transcribe_whisper",
        input_json={"source_id": source_id, "source_version": source_version, "audio": audio_rel},
    )

    try:
        artifacts = transcribe_and_store(source_id, source_version, str(audio_rel))
        manifest.setdefault("artifacts", {}).update(
            {
                "transcript": artifacts["transcript"],
                "segments": artifacts["segments"],
            }
        )
        manifest.setdefault("steps", {})["transcribe_whisper"] = {
            "status": "done",
            "segment_count": artifacts["segment_count"],
            "backend": artifacts.get("backend"),
        }
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane=str(job.get("lane", "transcribe")),
            component="transcribe_whisper",
            input_json={"run_id": run_id},
            output_json={"artifacts": artifacts},
        )
        from app.queue.jobs import enqueue_job
        enqueue_job("chunk_transcript", "oss20b", source_id, source_version)
        enqueue_job("diarize_audio", "transcribe", source_id, source_version)
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "transcribe")),
            component="transcribe_whisper",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
