"""Voiceprint enroll (MVP)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.core.ids import sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run
from app.modules.voiceprint.gallery import suggest_person


VOICEPRINTS_REL_PATH = "voiceprint/voiceprints.jsonl"


def _load_segments(text: str) -> List[Dict[str, object]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def enroll(segments: List[Dict[str, object]], source_id: str) -> List[Dict[str, object]]:
    speakers = {}
    for seg in segments:
        speaker = seg.get("speaker_local_id") or "UNKNOWN"
        speakers.setdefault(speaker, 0)
        speakers[speaker] += 1
    voiceprints = []
    for speaker, count in speakers.items():
        vp_id = sha256_text(f"{source_id}:{speaker}")
        voiceprints.append(
            {
                "voiceprint_id": vp_id,
                "speaker_local_id": speaker,
                "segment_count": count,
                "source_id": source_id,
            }
        )
    return voiceprints


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for voiceprint_enroll")

    if artifact_path(source_id, source_version, VOICEPRINTS_REL_PATH).exists():
        return

    segments_rel = manifest.get("artifacts", {}).get("segments_diarized") or manifest.get("artifacts", {}).get("segments")
    if not segments_rel:
        raise RuntimeError("segments artifact not found")

    seg_text = read_artifact(source_id, source_version, str(segments_rel))
    if seg_text is None:
        raise RuntimeError("segments artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "nemotron")),
        component="voiceprint_enroll",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    voiceprints = enroll(_load_segments(seg_text), source_id=source_id)
    lines = "\n".join(json.dumps(vp, ensure_ascii=True) for vp in voiceprints)
    write_artifact(source_id, source_version, VOICEPRINTS_REL_PATH, lines)

    if manifest.get("source_type") == "youtube" and len(voiceprints) == 1:
        channel = (manifest.get("metadata") or {}).get("channel")
        if channel:
            suggest_person(
                voiceprints[0]["voiceprint_id"],
                {
                    "title": str(channel),
                    "tags": ["auto-suggested", "youtube-channel"],
                    "notes": "Auto-suggested from YouTube channel metadata.",
                },
            )

    manifest.setdefault("artifacts", {})["voiceprints"] = VOICEPRINTS_REL_PATH
    manifest.setdefault("steps", {})["voiceprint_enroll"] = {"status": "done", "voiceprint_count": len(voiceprints)}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "nemotron")),
        component="voiceprint_enroll",
        input_json={"run_id": run_id},
        output_json={"voiceprint_count": len(voiceprints)},
    )

    enqueue_job("voiceprint_match", "nemotron", source_id, source_version)
