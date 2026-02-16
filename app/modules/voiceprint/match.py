"""Voiceprint match (MVP)."""

from __future__ import annotations

import json
from typing import Dict, List

from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run


MATCHES_REL_PATH = "voiceprint/matches.jsonl"


def _load_jsonl(text: str) -> List[Dict[str, object]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def match(voiceprints: List[Dict[str, object]], segments: List[Dict[str, object]]) -> List[Dict[str, object]]:
    vp_by_speaker = {vp.get("speaker_local_id"): vp for vp in voiceprints}
    matches = []
    for seg in segments:
        speaker = seg.get("speaker_local_id")
        vp = vp_by_speaker.get(speaker)
        if not vp:
            continue
        matches.append(
            {
                "segment_id": seg.get("segment_id"),
                "speaker_local_id": speaker,
                "voiceprint_id": vp.get("voiceprint_id"),
                "confidence": 0.5,
            }
        )
    return matches


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for voiceprint_match")

    if artifact_path(source_id, source_version, MATCHES_REL_PATH).exists():
        return

    voiceprints_rel = manifest.get("artifacts", {}).get("voiceprints")
    segments_rel = manifest.get("artifacts", {}).get("segments_diarized") or manifest.get("artifacts", {}).get("segments")
    if not voiceprints_rel or not segments_rel:
        raise RuntimeError("voiceprints/segments artifacts missing")

    vp_text = read_artifact(source_id, source_version, str(voiceprints_rel))
    seg_text = read_artifact(source_id, source_version, str(segments_rel))
    if vp_text is None or seg_text is None:
        raise RuntimeError("voiceprints/segments artifacts missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "nemotron")),
        component="voiceprint_match",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    voiceprints = _load_jsonl(vp_text)
    segments = _load_jsonl(seg_text)
    matches = match(voiceprints, segments)
    lines = "\n".join(json.dumps(m, ensure_ascii=True) for m in matches)
    write_artifact(source_id, source_version, MATCHES_REL_PATH, lines)

    manifest.setdefault("artifacts", {})["voiceprint_matches"] = MATCHES_REL_PATH
    manifest.setdefault("steps", {})["voiceprint_match"] = {"status": "done", "match_count": len(matches)}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "nemotron")),
        component="voiceprint_match",
        input_json={"run_id": run_id},
        output_json={"match_count": len(matches)},
    )

    enqueue_job("voiceprint_review", "nemotron", source_id, source_version)
