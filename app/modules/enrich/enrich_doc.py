"""Enrich document with summary/topics/entities via Ollama."""

from __future__ import annotations

import json
from typing import Dict

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import EnrichDocOutput
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run


SUMMARY_REL_PATH = "enrich/doc_summary.json"


def _prompt(text: str) -> str:
    return (
        "You are a helpful assistant. Return ONLY valid JSON with keys: "
        "summary_short, summary_long, topics, entities. "
        "summary_short should be 1-2 sentences. summary_long 3-6 sentences. "
        "topics and entities are arrays of short strings.\n\n"
        f"Text:\n{text}\n"
    )


def enrich(text: str) -> EnrichDocOutput:
    settings = load_settings()
    return generate_json(_prompt(text), settings.ollama_model_strong, EnrichDocOutput)


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for enrich_doc")

    existing = artifact_path(source_id, source_version, SUMMARY_REL_PATH)
    if existing.exists():
        return

    canonical_rel = manifest.get("artifacts", {}).get("canonical_text")
    if not canonical_rel:
        raise RuntimeError("canonical_text artifact not found")

    text = read_artifact(source_id, source_version, str(canonical_rel))
    if text is None:
        raise RuntimeError("canonical_text artifact missing on disk")

    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="enrich_doc",
        input_json={"source_id": source_id, "source_version": source_version},
        model=load_settings().ollama_model_strong,
    )

    try:
        output = enrich(text)
        payload = output.model_dump()
        write_artifact(source_id, source_version, SUMMARY_REL_PATH, json.dumps(payload, ensure_ascii=True))

        manifest.setdefault("artifacts", {})["doc_summary"] = SUMMARY_REL_PATH
        manifest.setdefault("steps", {})["enrich_doc"] = {"status": "done"}
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane=str(job.get("lane", "oss20b")),
            component="enrich_doc",
            input_json={"run_id": run_id},
            output_json=payload,
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "oss20b")),
            component="enrich_doc",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
