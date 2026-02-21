"""Ontology rule registry and validation helpers for GraphRAG."""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List, Tuple


DEFAULT_ONTOLOGY_RULES: List[Dict[str, str]] = [
    {
        "predicate": "mentions",
        "domain_type": "Document",
        "range_type": "Entity",
        "description": "Doc mentions entity",
    },
    {
        "predicate": "mentions",
        "domain_type": "Entity",
        "range_type": "Entity",
        "description": "Entity mention/link in conversational sources",
    },
    {
        "predicate": "has_topic",
        "domain_type": "Document",
        "range_type": "Topic",
        "description": "Doc has topic",
    },
    {
        "predicate": "related_to",
        "domain_type": "Entity",
        "range_type": "Entity",
        "description": "Entity related to",
    },
    {
        "predicate": "describes",
        "domain_type": "Person",
        "range_type": "Entity",
        "description": "Person describes EBUCore node",
    },
    {
        "predicate": "affiliated_with",
        "domain_type": "Person",
        "range_type": "Organisation",
        "description": "Person affiliation",
    },
]

_ENTITY_TYPE_ALIASES = {
    "document": "Document",
    "doc": "Document",
    "entity": "Entity",
    "topic": "Topic",
    "person": "Person",
    "org": "Organisation",
    "organization": "Organisation",
    "organisation": "Organisation",
}


def normalize_predicate(value: object) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"[\s\-]+", "_", raw)
    raw = re.sub(r"[^a-z0-9_]", "", raw)
    return raw.strip("_")


def normalize_entity_type(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Entity"
    key = re.sub(r"[^a-z0-9]", "", raw.lower())
    if key in _ENTITY_TYPE_ALIASES:
        return _ENTITY_TYPE_ALIASES[key]
    return raw[:1].upper() + raw[1:]


def canonical_rules(rows: Iterable[Dict[str, object]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for row in rows:
        predicate = normalize_predicate(row.get("predicate"))
        if not predicate:
            continue
        domain_type = normalize_entity_type(row.get("domain_type"))
        range_type = normalize_entity_type(row.get("range_type"))
        description = str(row.get("description") or "").strip()
        key = (predicate, domain_type, range_type)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "predicate": predicate,
                "domain_type": domain_type,
                "range_type": range_type,
                "description": description,
            }
        )
    return out


def canonical_default_rules() -> List[Dict[str, str]]:
    return canonical_rules(DEFAULT_ONTOLOGY_RULES)


def render_allowed_predicate_lines(rules: Iterable[Dict[str, object]]) -> str:
    items = canonical_rules(rules)
    if not items:
        items = canonical_default_rules()
    lines = []
    for row in items:
        lines.append(f"- {row['predicate']} ({row['domain_type']} -> {row['range_type']})")
    return "\n".join(lines)


def _type_matches(actual: str, expected: str) -> bool:
    a = normalize_entity_type(actual)
    e = normalize_entity_type(expected)
    if e == "Entity":
        return True
    return a == e


def validate_relations(
    relations: List[Dict[str, object]],
    entity_types: Dict[str, str],
    rules: Iterable[Dict[str, object]],
) -> Dict[str, object]:
    canonical = canonical_rules(rules)
    if not canonical:
        canonical = canonical_default_rules()

    by_predicate: Dict[str, List[Tuple[str, str]]] = {}
    for row in canonical:
        by_predicate.setdefault(row["predicate"], []).append((row["domain_type"], row["range_type"]))

    valid: List[Dict[str, object]] = []
    invalid: List[Dict[str, object]] = []

    for row in relations:
        relation = dict(row)
        predicate = normalize_predicate(relation.get("predicate"))
        relation["predicate"] = predicate
        subj_id = str(relation.get("subj_entity_id") or "").strip()
        obj_id = str(relation.get("obj_entity_id") or "").strip()
        if not predicate:
            relation["_validation_error"] = "missing_predicate"
            invalid.append(relation)
            continue
        subj_type = normalize_entity_type(entity_types.get(subj_id) or "Entity")
        obj_type = normalize_entity_type(entity_types.get(obj_id) or "Entity")
        relation["_subj_type"] = subj_type
        relation["_obj_type"] = obj_type

        options = by_predicate.get(predicate)
        if not options:
            relation["_validation_error"] = "predicate_not_in_ontology"
            invalid.append(relation)
            continue

        matched = False
        for domain_type, range_type in options:
            if _type_matches(subj_type, domain_type) and _type_matches(obj_type, range_type):
                matched = True
                break
        if not matched:
            relation["_validation_error"] = "domain_range_mismatch"
            invalid.append(relation)
            continue
        valid.append(relation)

    summary = {
        "total": len(relations),
        "valid": len(valid),
        "invalid": len(invalid),
        "rules": len(canonical),
    }
    return {
        "rules": canonical,
        "valid_relations": valid,
        "invalid_relations": invalid,
        "summary": summary,
    }


def to_jsonl(rows: Iterable[Dict[str, object]]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=True) for row in rows)
