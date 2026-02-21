"""Generate cleaned transcript + summary markdown from transcript artifacts."""

from __future__ import annotations

import json
import os
from typing import Dict, List

from app.clients.ollama_client import generate_json
from app.core.config import load_settings
from app.core.manifest import get_manifest, upsert_manifest
from app.core.models import TranscriptMarkdownOutput
from app.core.prompts import render_prompt
from app.core.storage import artifact_path, read_artifact, write_artifact
from app.core.timeutil import utc_now
from app.queue.logs import log_run


TRANSCRIPT_MD_REL_PATH = "transcript/summary.md"
TRANSCRIPT_JSON_REL_PATH = "transcript/summary.json"


def _max_chars() -> int:
    raw = str(os.getenv("AURORA_TRANSCRIPT_MARKDOWN_MAX_CHARS", "24000")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 24000
    return max(4000, min(120000, value))


def _load_jsonl(text: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _plain_transcript_from_segments(segments: List[Dict[str, object]]) -> str:
    parts: List[str] = []
    for seg in segments:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        parts.append(text)
    return "\n".join(parts).strip()


def _extract_intake_meta(manifest: Dict[str, object]) -> Dict[str, str]:
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    intake = metadata.get("intake")
    if not isinstance(intake, dict):
        return {}
    source_meta = intake.get("source_metadata")
    source_meta = source_meta if isinstance(source_meta, dict) else {}
    out = {
        "speaker": str(source_meta.get("speaker") or "").strip(),
        "organization": str(source_meta.get("organization") or "").strip(),
        "event_date": str(source_meta.get("event_date") or "").strip(),
        "context": str(intake.get("context") or "").strip(),
    }
    tags = intake.get("tags")
    if isinstance(tags, list):
        out["tags"] = ", ".join(str(t).strip() for t in tags if str(t).strip())
    return out


def _to_markdown(
    source_id: str,
    source_version: str,
    output: TranscriptMarkdownOutput,
    meta: Dict[str, str],
    clipped: bool,
) -> str:
    lines: List[str] = [
        "# Transcript Summary",
        "",
        "## Source",
        f"- source_id: `{source_id}`",
        f"- source_version: `{source_version}`",
        f"- generated_at: `{utc_now().isoformat()}`",
    ]
    if meta.get("speaker"):
        lines.append(f"- speaker: {meta['speaker']}")
    if meta.get("organization"):
        lines.append(f"- organization: {meta['organization']}")
    if meta.get("event_date"):
        lines.append(f"- event_date: {meta['event_date']}")
    if meta.get("tags"):
        lines.append(f"- tags: {meta['tags']}")
    if meta.get("context"):
        lines.append(f"- context: {meta['context']}")
    if clipped:
        lines.append("- note: transcript input was clipped for prompt size limits")

    lines.extend(
        [
            "",
            "## Short Summary",
            output.summary_short.strip(),
            "",
            "## Long Summary",
            output.summary_long.strip(),
            "",
            "## Clean Transcript",
            output.cleaned_transcript.strip(),
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def handle_job(job: Dict[str, object]) -> None:
    source_id = str(job["source_id"])
    source_version = str(job["source_version"])

    manifest = get_manifest(source_id, source_version)
    if not manifest:
        raise RuntimeError("Manifest not found for transcript_markdown")

    if artifact_path(source_id, source_version, TRANSCRIPT_MD_REL_PATH).exists():
        return

    transcript_rel = manifest.get("artifacts", {}).get("transcript")
    segments_rel = manifest.get("artifacts", {}).get("segments")
    transcript_text = ""

    if segments_rel:
        seg_text = read_artifact(source_id, source_version, str(segments_rel))
        if seg_text:
            transcript_text = _plain_transcript_from_segments(_load_jsonl(seg_text))
    if not transcript_text and transcript_rel:
        raw = read_artifact(source_id, source_version, str(transcript_rel))
        if raw:
            transcript_text = str(raw).strip()
    if not transcript_text:
        raise RuntimeError("transcript/segments artifact missing for transcript_markdown")

    max_chars = _max_chars()
    clipped = len(transcript_text) > max_chars
    prompt_text = transcript_text[:max_chars]
    settings = load_settings()
    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="transcript_markdown",
        input_json={
            "source_id": source_id,
            "source_version": source_version,
            "input_chars": len(transcript_text),
            "prompt_chars": len(prompt_text),
            "clipped": clipped,
        },
        model=settings.ollama_model_fast,
    )

    try:
        output = generate_json(
            render_prompt("transcript_markdown", source_id=source_id, transcript_text=prompt_text),
            settings.ollama_model_fast,
            TranscriptMarkdownOutput,
        )
        payload = output.model_dump()
        payload["source_id"] = source_id
        payload["source_version"] = source_version
        payload["input_chars"] = len(transcript_text)
        payload["prompt_chars"] = len(prompt_text)
        payload["clipped"] = clipped

        meta = _extract_intake_meta(manifest)
        md = _to_markdown(source_id, source_version, output, meta=meta, clipped=clipped)
        write_artifact(source_id, source_version, TRANSCRIPT_JSON_REL_PATH, json.dumps(payload, ensure_ascii=True))
        write_artifact(source_id, source_version, TRANSCRIPT_MD_REL_PATH, md)

        manifest.setdefault("artifacts", {})["transcript_summary_json"] = TRANSCRIPT_JSON_REL_PATH
        manifest.setdefault("artifacts", {})["transcript_summary_md"] = TRANSCRIPT_MD_REL_PATH
        manifest.setdefault("steps", {})["transcript_markdown"] = {
            "status": "done",
            "input_chars": len(transcript_text),
            "prompt_chars": len(prompt_text),
            "clipped": clipped,
        }
        manifest["updated_at"] = utc_now().isoformat()
        upsert_manifest(source_id, source_version, manifest)

        log_run(
            lane=str(job.get("lane", "oss20b")),
            component="transcript_markdown",
            input_json={"run_id": run_id},
            output_json={
                "summary_short_len": len(output.summary_short),
                "summary_long_len": len(output.summary_long),
                "cleaned_transcript_len": len(output.cleaned_transcript),
            },
        )
    except Exception as exc:
        log_run(
            lane=str(job.get("lane", "oss20b")),
            component="transcript_markdown",
            input_json={"run_id": run_id},
            error=str(exc),
        )
        raise
