"""Helpers for stable prompt serialization and size control."""

from __future__ import annotations

import json
from typing import Dict, List, Tuple

from app.core.textnorm import normalize_whitespace


def serialize_for_prompt(
    payload: object,
    max_chars: int = 12000,
    max_list_items: int = 24,
    max_text_chars: int = 700,
) -> Tuple[str, Dict[str, object]]:
    raw = _json_dump(payload)
    prepared = _prepare(
        payload,
        key="root",
        depth=0,
        max_depth=6,
        max_list_items=max_list_items,
        max_text_chars=max_text_chars,
    )
    rendered = _json_dump(prepared)
    degraded = False

    if len(rendered) > max_chars:
        degraded = True
        prepared = _prepare(
            payload,
            key="root",
            depth=0,
            max_depth=4,
            max_list_items=max(6, max_list_items // 2),
            max_text_chars=max(220, max_text_chars // 2),
        )
        rendered = _json_dump(prepared)

    if len(rendered) > max_chars:
        degraded = True
        preview_len = max(40, max_chars - 220)
        while True:
            rendered = _json_dump(
                {
                    "truncated": True,
                    "note": f"payload clipped for prompt (raw_chars={len(raw)})",
                    "preview": rendered[:preview_len],
                }
            )
            if len(rendered) <= max_chars or preview_len <= 40:
                break
            preview_len = max(40, preview_len - 40)

    meta: Dict[str, object] = {
        "chars_raw": len(raw),
        "chars_final": len(rendered),
        "truncated": len(raw) != len(rendered) or degraded,
    }
    return rendered, meta


def _prepare(
    value: object,
    key: str,
    depth: int,
    max_depth: int,
    max_list_items: int,
    max_text_chars: int,
) -> object:
    if depth >= max_depth:
        return _truncate_text(str(value), max_text_chars // 2)

    if isinstance(value, dict):
        out: Dict[str, object] = {}
        for child_key in sorted(value.keys(), key=lambda x: str(x)):
            norm_key = str(child_key)
            out[norm_key] = _prepare(
                value.get(child_key),
                key=norm_key,
                depth=depth + 1,
                max_depth=max_depth,
                max_list_items=max_list_items,
                max_text_chars=max_text_chars,
            )
        return out

    if isinstance(value, list):
        trimmed = value[:max_list_items]
        out_list: List[object] = [
            _prepare(
                item,
                key=key,
                depth=depth + 1,
                max_depth=max_depth,
                max_list_items=max_list_items,
                max_text_chars=max_text_chars,
            )
            for item in trimmed
        ]
        hidden = len(value) - len(trimmed)
        if hidden > 0:
            out_list.append({"_truncated_items": hidden})
        return out_list

    if isinstance(value, str):
        if _is_large_text_key(key):
            return _truncate_text(value, max_text_chars)
        return _truncate_text(value, min(220, max_text_chars))

    if value is None:
        return None

    if isinstance(value, (int, float, bool)):
        return value

    return _truncate_text(str(value), min(220, max_text_chars))


def _is_large_text_key(key: str) -> bool:
    key = str(key).lower()
    hints = ("text", "snippet", "summary", "answer", "content", "reason")
    return any(h in key for h in hints)


def _truncate_text(text: str, limit: int) -> str:
    value = normalize_whitespace(text)
    if len(value) <= limit:
        return value
    suffix = "...<truncated>"
    keep = max(0, limit - len(suffix))
    return value[:keep].rstrip() + suffix


def _json_dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))
