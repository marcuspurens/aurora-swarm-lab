"""Voice gallery storage and metadata editing (EBUCore+ aligned)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from app.core.storage import artifact_root
from app.queue.jobs import enqueue_job


GALLERY_FILE = "voice_gallery.json"


def _gallery_path() -> Path:
    return artifact_root() / GALLERY_FILE


def load_gallery() -> Dict[str, Dict[str, object]]:
    path = _gallery_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_gallery(data: Dict[str, Dict[str, object]]) -> None:
    path = _gallery_path()
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def _scan_voiceprints() -> Dict[str, Dict[str, object]]:
    gallery: Dict[str, Dict[str, object]] = {}
    root = artifact_root()
    for vp_file in root.rglob("voiceprints.jsonl"):
        try:
            for line in vp_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                vp = json.loads(line)
                vp_id = vp.get("voiceprint_id")
                if not vp_id:
                    continue
                gallery.setdefault(
                    vp_id,
                    {
                        "voiceprint_id": vp_id,
                        "speaker_local_id": vp.get("speaker_local_id"),
                        "segment_count": vp.get("segment_count"),
                        "source_id": vp.get("source_id"),
                    },
                )
        except Exception:
            continue
    return gallery


def list_voiceprints() -> List[Dict[str, object]]:
    data = load_gallery()
    if not data:
        data = _scan_voiceprints()
        if data:
            save_gallery(data)
            _enqueue_voice_gallery_jobs()
    return list(data.values())


def _enqueue_voice_gallery_jobs() -> None:
    enqueue_job("embed_voice_gallery", "oss20b", "voice_gallery", "latest")
    enqueue_job("graph_from_voice_gallery", "io", "voice_gallery", "latest")


def _dedupe_key(item: object) -> str:
    if isinstance(item, (dict, list)):
        return json.dumps(item, sort_keys=True, ensure_ascii=True)
    return str(item)


def _merge_list(existing: object, incoming: object) -> List[object]:
    items: List[object] = []
    if isinstance(existing, list):
        items.extend(i for i in existing if i is not None)
    if isinstance(incoming, list):
        items.extend(i for i in incoming if i is not None)
    seen = set()
    merged: List[object] = []
    for item in items:
        key = _dedupe_key(item)
        if key in seen:
            continue
        merged.append(item)
        seen.add(key)
    return merged


def _merge_dict(existing: object, incoming: object) -> Dict[str, object]:
    merged: Dict[str, object] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged


def _apply_fields(entry: Dict[str, object], fields: Dict[str, object], overwrite: bool) -> None:
    allowed = {
        "given_name",
        "family_name",
        "display_name",
        "full_name",
        "title",
        "role",
        "roles",
        "affiliation",
        "organizations",
        "aliases",
        "tags",
        "notes",
        "person_id",
        "birth_date",
        "death_date",
        "gender",
        "nationality",
        "language",
        "country",
        "city",
        "bio",
        "homepage",
        "image",
        "same_as",
        "identifiers",
        "contacts",
        "socials",
        "credits",
        "source_refs",
        "confidence",
        "ebucore",
    }
    list_fields = {"aliases", "tags", "roles", "organizations", "same_as", "identifiers", "contacts", "socials"}
    dict_fields = {"credits", "source_refs", "ebucore"}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in list_fields:
            entry[k] = _merge_list(entry.get(k), v)
            continue
        if k in dict_fields:
            if overwrite or not entry.get(k):
                entry[k] = _merge_dict(entry.get(k), v)
            continue
        if not overwrite and entry.get(k):
            continue
        entry[k] = v


def upsert_person(voiceprint_id: str, fields: Dict[str, object]) -> Dict[str, object]:
    data = load_gallery()
    entry = data.get(voiceprint_id, {"voiceprint_id": voiceprint_id})

    _apply_fields(entry, fields, overwrite=True)
    if not entry.get("person_id"):
        entry["person_id"] = f"person_{voiceprint_id}"

    data[voiceprint_id] = entry
    save_gallery(data)
    _enqueue_voice_gallery_jobs()
    return entry


def suggest_person(voiceprint_id: str, fields: Dict[str, object]) -> Dict[str, object]:
    data = load_gallery()
    entry = data.get(voiceprint_id, {"voiceprint_id": voiceprint_id})

    _apply_fields(entry, fields, overwrite=False)
    if not entry.get("person_id"):
        entry["person_id"] = f"person_{voiceprint_id}"

    data[voiceprint_id] = entry
    save_gallery(data)
    _enqueue_voice_gallery_jobs()
    return entry
