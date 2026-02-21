"""Intake document: extract text, store artifacts, update manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from app.core.ids import make_source_id, parse_source_id, sha256_file
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import read_artifact, write_artifact, write_artifact_bytes
from app.core.timeutil import utc_now
from app.modules.security.ingest_allowlist import ensure_ingest_path_allowed
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run
from app.modules.doc_extract.extract_doc import extract


RAW_DOC_PATH = "raw/source"
CANONICAL_TEXT_PATH = "text/canonical.txt"


def enqueue(path: str) -> str:
    abs_path = str(ensure_ingest_path_allowed(Path(path), source="ingest_doc_enqueue"))
    source_id = make_source_id("file", abs_path)
    source_version = sha256_file(Path(abs_path))
    return enqueue_job("ingest_doc", "io", source_id, source_version)


def ingest_doc(path: str, source_id: str, source_version: str) -> Dict[str, object]:
    existing = get_manifest(source_id, source_version)
    if existing:
        existing_text = read_artifact(source_id, source_version, CANONICAL_TEXT_PATH)
        if existing_text:
            return existing

    file_path = Path(path)
    text = extract(str(file_path))

    raw_rel = f"{RAW_DOC_PATH}{file_path.suffix.lower()}"
    write_artifact_bytes(source_id, source_version, raw_rel, file_path.read_bytes())
    write_artifact(source_id, source_version, CANONICAL_TEXT_PATH, text)

    manifest = dict(existing or {})
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    artifacts.update(
        {
            "raw_doc": raw_rel,
            "canonical_text": CANONICAL_TEXT_PATH,
        }
    )
    steps = manifest.get("steps")
    if not isinstance(steps, dict):
        steps = {}
    steps["ingest_doc"] = {"status": "done"}
    manifest.update(
        {
            "source_id": source_id,
            "source_version": source_version,
            "source_type": "file",
            "source_uri": str(file_path),
            "artifacts": artifacts,
            "stats": {
                "text_chars": len(text),
                "text_words": len(text.split()) if text else 0,
            },
            "updated_at": utc_now().isoformat(),
            "steps": steps,
        }
    )
    upsert_manifest(source_id, source_version, manifest)
    enqueue_job("chunk_text", "oss20b", source_id, source_version)
    return manifest


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])
    kind, value = parse_source_id(source_id)
    if kind != "file":
        raise ValueError(f"Expected file source_id, got {source_id}")

    run_id = log_run(
        lane=str(job.get("lane", "io")),
        component="intake_doc",
        input_json={"source_id": source_id, "source_version": source_version, "path": value},
    )

    try:
        manifest = ingest_doc(value, source_id, source_version)
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_doc",
            input_json={"run_id": run_id},
            output_json={"artifacts": manifest.get("artifacts", {})},
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_doc",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
