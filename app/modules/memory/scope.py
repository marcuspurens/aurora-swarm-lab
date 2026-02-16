"""Scope helpers for isolating memory reads and writes."""

from __future__ import annotations

from typing import Dict

from app.core.textnorm import normalize_identifier

SCOPE_KEYS = ("user_id", "project_id", "session_id")


def normalize_scope(
    user_id: object = None,
    project_id: object = None,
    session_id: object = None,
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    raw = {
        "user_id": user_id,
        "project_id": project_id,
        "session_id": session_id,
    }
    for key, value in raw.items():
        normalized = normalize_identifier(value, max_len=120)
        if normalized:
            out[key] = normalized
    return out


def apply_scope_to_source_refs(source_refs: Dict[str, object], scope: Dict[str, str]) -> Dict[str, object]:
    refs = dict(source_refs or {})
    if not scope:
        return refs

    nested_scope = refs.get("scope")
    if not isinstance(nested_scope, dict):
        nested_scope = {}

    for key, value in scope.items():
        refs[key] = value
        nested_scope[key] = value

    refs["scope"] = nested_scope
    return refs


def scope_from_source_refs(source_refs: object) -> Dict[str, str]:
    if not isinstance(source_refs, dict):
        return {}
    out: Dict[str, str] = {}
    nested = source_refs.get("scope")
    nested_scope = nested if isinstance(nested, dict) else {}
    for key in SCOPE_KEYS:
        candidate = source_refs.get(key)
        if not candidate and nested_scope:
            candidate = nested_scope.get(key)
        normalized = normalize_identifier(candidate, max_len=120)
        if normalized:
            out[key] = normalized
    return out


def scope_matches(source_refs: object, scope: Dict[str, str]) -> bool:
    if not scope:
        return True
    item_scope = scope_from_source_refs(source_refs)
    for key, value in scope.items():
        if item_scope.get(key) != value:
            return False
    return True
