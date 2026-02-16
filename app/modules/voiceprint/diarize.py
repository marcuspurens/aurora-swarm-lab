"""Diarization using pyannote (with fallback stub)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.diarization_client import DiarizationSegment, run_diarization
from app.core.config import load_settings
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run
from app.queue.jobs import enqueue_job


DIARIZED_REL_PATH = "transcript/segments_diarized.jsonl"


def _load_segments(text: str) -> List[Dict[str, object]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _assign_speakers(segments: List[Dict[str, object]], diarization: List[DiarizationSegment]) -> List[Dict[str, object]]:
    diarized = []
    for seg in segments:
        start_ms = int(seg.get("start_ms") or 0)
        end_ms = int(seg.get("end_ms") or 0)
        best = None
        best_overlap = -1
        for d in diarization:
            overlap = max(0, min(end_ms, d.end_ms) - max(start_ms, d.start_ms))
            if overlap > best_overlap:
                best_overlap = overlap
                best = d
        seg = dict(seg)
        if best is not None and best_overlap > 0:
            seg["speaker_local_id"] = best.speaker
        else:
            seg["speaker_local_id"] = seg.get("speaker_local_id") or "UNKNOWN"
        diarized.append(seg)
    return diarized


def _stub_diarize(segments: List[Dict[str, object]]) -> List[Dict[str, object]]:
    diarized = []
    for seg in segments:
        seg = dict(seg)
        seg["speaker_local_id"] = seg.get("speaker_local_id") or "SPEAKER_1"
        if seg["speaker_local_id"] == "UNKNOWN":
            seg["speaker_local_id"] = "SPEAKER_1"
        diarized.append(seg)
    return diarized


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for diarize")

    if artifact_path(source_id, source_version, DIARIZED_REL_PATH).exists():
        return

    segments_rel = manifest.get("artifacts", {}).get("segments")
    audio_rel = manifest.get("artifacts", {}).get("audio")
    if not segments_rel or not audio_rel:
        raise RuntimeError("segments/audio artifact not found")

    seg_text = read_artifact(source_id, source_version, str(segments_rel))
    if seg_text is None:
        raise RuntimeError("segments artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "transcribe")),
        component="diarize_audio",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    segments = _load_segments(seg_text)
    settings = load_settings()
    diarized: List[Dict[str, object]]
    try:
        if settings.pyannote_token:
            audio_path = str(artifact_path(source_id, source_version, str(audio_rel)))
            diarization = run_diarization(audio_path)
            diarized = _assign_speakers(segments, diarization)
        else:
            diarized = _stub_diarize(segments)
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "transcribe")),
            component="diarize_audio",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise

    lines = "\n".join(json.dumps(s, ensure_ascii=True) for s in diarized)
    write_artifact(source_id, source_version, DIARIZED_REL_PATH, lines)

    manifest.setdefault("artifacts", {})["segments_diarized"] = DIARIZED_REL_PATH
    manifest.setdefault("steps", {})["diarize_audio"] = {"status": "done", "segment_count": len(diarized)}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "transcribe")),
        component="diarize_audio",
        input_json={"run_id": run_id},
        output_json={"segment_count": len(diarized)},
    )

    enqueue_job("voiceprint_enroll", "nemotron", source_id, source_version)
