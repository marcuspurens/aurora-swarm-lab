"""Intake YouTube: extract audio, store artifacts, update manifest, enqueue transcription."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

from app.clients.youtube_client import extract_audio, get_video_info
from app.core.ids import make_source_id, parse_source_id
from app.core.ids import sha256_file
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


AUDIO_REL_PATH = "audio/source.m4a"


def compute_source_version(url: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "source.m4a"
        downloaded = extract_audio(url, str(out_path))
        return sha256_file(downloaded)


def enqueue(url: str) -> str:
    info = get_video_info(url)
    video_id = str(info.get("id") or "unknown")
    source_id = make_source_id("youtube", video_id)
    source_version = compute_source_version(url)
    return enqueue_job("ingest_youtube", "io", source_id, source_version)


def ingest_youtube(video_id: str, source_id: str, source_version: str) -> Dict[str, object]:
    existing = get_manifest(source_id, source_version)
    if existing:
        audio_path = artifact_path(source_id, source_version, AUDIO_REL_PATH)
        if audio_path.exists():
            return existing

    url = f"https://www.youtube.com/watch?v={video_id}"
    info = get_video_info(url)
    title = info.get("title")
    resolved_id = str(info.get("id") or video_id)

    audio_path = artifact_path(source_id, source_version, AUDIO_REL_PATH)
    downloaded = extract_audio(url, str(audio_path))
    if downloaded != audio_path:
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(Path(downloaded).read_bytes())

    manifest = {
        "source_id": source_id,
        "source_version": source_version,
        "source_type": "youtube",
        "source_uri": url,
        "title": title,
        "artifacts": {
            "audio": AUDIO_REL_PATH,
        },
        "metadata": {
            "youtube_id": resolved_id,
            "channel": info.get("uploader"),
        },
        "updated_at": utc_now().isoformat(),
        "steps": {
            "ingest_youtube": {
                "status": "done",
            }
        },
    }
    upsert_manifest(source_id, source_version, manifest)

    enqueue_job("denoise_audio", "transcribe", source_id, source_version)
    return manifest


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])
    kind, value = parse_source_id(source_id)
    if kind != "youtube":
        raise ValueError(f"Expected youtube source_id, got {source_id}")

    run_id = log_run(
        lane=str(job.get("lane", "io")),
        component="intake_youtube",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    try:
        manifest = ingest_youtube(value, source_id, source_version)
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_youtube",
            input_json={"run_id": run_id},
            output_json={"artifacts": manifest.get("artifacts", {})},
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_youtube",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
