"""Embed voice gallery metadata for retrieval."""

from __future__ import annotations

import json
from typing import Dict, List

from app.clients.ollama_client import embed
from app.core.config import load_settings
from app.core.ids import sha256_text
from app.modules.voiceprint.gallery import load_gallery
from app.modules.embeddings.embedding_store import get_embedding_hashes, upsert_embedding
from app.queue.logs import log_run


def _entry_text(entry: Dict[str, object]) -> str:
    parts: List[str] = []
    for key in (
        "display_name",
        "full_name",
        "given_name",
        "family_name",
        "title",
        "role",
        "affiliation",
        "bio",
        "notes",
    ):
        value = entry.get(key)
        if value:
            parts.append(f"{key}: {value}")
    for list_key in ("roles", "organizations", "aliases", "tags", "same_as"):
        value = entry.get(list_key)
        if isinstance(value, list) and value:
            parts.append(f"{list_key}: " + ", ".join(str(v) for v in value))
    for dict_key in ("identifiers", "contacts", "socials", "source_refs"):
        value = entry.get(dict_key)
        if value:
            parts.append(f"{dict_key}: {json.dumps(value, ensure_ascii=True)}")
    ebucore = entry.get("ebucore")
    if ebucore:
        parts.append(f"ebucore: {json.dumps(ebucore, ensure_ascii=True)}")
    return "\n".join(parts).strip()


def handle_job(job: Dict[str, object]) -> None:
    settings = load_settings()
    if not settings.embeddings_enabled:
        return

    run_id = log_run(
        lane=str(job.get("lane", "oss20b")),
        component="embed_voice_gallery",
        input_json={"source_id": job.get("source_id"), "source_version": job.get("source_version")},
    )

    data = load_gallery()
    if not data:
        return

    existing_hashes = get_embedding_hashes("voice_gallery")
    embedded = 0
    for vp_id, entry in data.items():
        text = _entry_text(entry)
        if not text:
            continue
        segment_id = f"voiceprint:{vp_id}"
        text_hash = sha256_text(text)
        if existing_hashes.get(segment_id) == text_hash:
            continue
        vector = embed(text)
        upsert_embedding(
            {
                "doc_id": "voice_gallery",
                "segment_id": segment_id,
                "source_id": "voice_gallery",
                "source_version": str(job.get("source_version") or "latest"),
                "text": text,
                "text_hash": text_hash,
                "embedding": vector,
                "start_ms": None,
                "end_ms": None,
                "speaker": None,
                "source_refs": {"voiceprint_id": vp_id},
            }
        )
        embedded += 1

    log_run(
        lane=str(job.get("lane", "oss20b")),
        component="embed_voice_gallery",
        input_json={"run_id": run_id},
        output_json={"embedded": embedded},
    )
