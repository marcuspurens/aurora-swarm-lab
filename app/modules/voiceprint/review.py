"""Voiceprint review summary (MVP)."""

from __future__ import annotations

import json
from typing import Dict

from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run


REVIEW_REL_PATH = "voiceprint/review.json"


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for voiceprint_review")

    if artifact_path(source_id, source_version, REVIEW_REL_PATH).exists():
        return

    matches_rel = manifest.get("artifacts", {}).get("voiceprint_matches")
    if not matches_rel:
        raise RuntimeError("voiceprint_matches artifact not found")

    m_text = read_artifact(source_id, source_version, str(matches_rel))
    if m_text is None:
        raise RuntimeError("voiceprint_matches artifact missing on disk")

    count = len([line for line in m_text.splitlines() if line.strip()])
    summary = {"match_count": count}

    run_id = log_run(
        lane=str(job.get("lane", "nemotron")),
        component="voiceprint_review",
        input_json={"source_id": source_id, "source_version": source_version},
    )

    write_artifact(source_id, source_version, REVIEW_REL_PATH, json.dumps(summary, ensure_ascii=True))
    manifest.setdefault("artifacts", {})["voiceprint_review"] = REVIEW_REL_PATH
    manifest.setdefault("steps", {})["voiceprint_review"] = {"status": "done", "match_count": count}
    manifest["updated_at"] = utc_now().isoformat()
    upsert_manifest(source_id, source_version, manifest)

    log_run(
        lane=str(job.get("lane", "nemotron")),
        component="voiceprint_review",
        input_json={"run_id": run_id},
        output_json=summary,
    )
