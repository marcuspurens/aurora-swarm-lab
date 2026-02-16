"""Intake URL: scrape, extract readable text, store artifacts, update manifest."""

from __future__ import annotations

from typing import Dict

from app.core.ids import make_source_id, parse_source_id, sha256_text
from app.core.manifest import get_manifest, upsert_manifest
from app.core.storage import read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run
from app.modules.scrape.readable_text import extract
from app.modules.scrape.scrape_url import scrape


RAW_HTML_PATH = "raw/url.html"
CANONICAL_TEXT_PATH = "text/canonical.txt"


def compute_source_version(url: str) -> str:
    html = scrape(url)
    text = extract(html)
    return sha256_text(text)


def enqueue(url: str) -> str:
    source_id = make_source_id("url", url)
    source_version = compute_source_version(url)
    return enqueue_job("ingest_url", "io", source_id, source_version)


def ingest_url(url: str, source_id: str, source_version: str) -> Dict[str, object]:
    existing = get_manifest(source_id, source_version)
    if existing:
        existing_text = read_artifact(source_id, source_version, CANONICAL_TEXT_PATH)
        if existing_text:
            return existing

    html = scrape(url)
    text = extract(html)

    write_artifact(source_id, source_version, RAW_HTML_PATH, html)
    write_artifact(source_id, source_version, CANONICAL_TEXT_PATH, text)

    manifest = {
        "source_id": source_id,
        "source_version": source_version,
        "source_type": "url",
        "source_uri": url,
        "artifacts": {
            "raw_html": RAW_HTML_PATH,
            "canonical_text": CANONICAL_TEXT_PATH,
        },
        "stats": {
            "text_chars": len(text),
            "text_words": len(text.split()) if text else 0,
        },
        "updated_at": utc_now().isoformat(),
        "steps": {
            "ingest_url": {
                "status": "done",
            }
        },
    }
    upsert_manifest(source_id, source_version, manifest)
    enqueue_job("chunk_text", "oss20b", source_id, source_version)
    return manifest


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])
    kind, value = parse_source_id(source_id)
    if kind != "url":
        raise ValueError(f"Expected url source_id, got {source_id}")

    run_id = log_run(
        lane=str(job.get("lane", "io")),
        component="intake_url",
        input_json={"source_id": source_id, "source_version": source_version, "url": value},
    )

    try:
        manifest = ingest_url(value, source_id, source_version)
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_url",
            input_json={"run_id": run_id},
            output_json={"artifacts": manifest.get("artifacts", {})},
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "io")),
            component="intake_url",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
