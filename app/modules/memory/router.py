"""Deterministic memory routing and explicit remember parsing."""

from __future__ import annotations

import re
from typing import Dict, Optional

from app.core.textnorm import normalize_user_text


MEMORY_KINDS = {"semantic", "episodic", "procedural"}

_REMEMBER_RE = re.compile(
    r"^\s*(?:remember(?:\s+this|\s+that)?|kom\s+ih[åa]g(?:\s+(?:detta|det\s+h[aä]r))?)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)
_KIND_RE = re.compile(r"^(?:as\s+)?(?P<kind>semantic|episodic|procedural)\s*[:\-]?\s+(?P<body>.+)$", re.IGNORECASE)

_PROCEDURAL_HINTS = (
    "how to",
    "steps",
    "step by step",
    "workflow",
    "run this",
    "command",
    "always do",
    "procedure",
    "playbook",
    "hur man",
    "steg",
    "arbetsflode",
    "arbetsflöde",
    "kommando",
    "alltid",
    "rutin",
)
_EPISODIC_HINTS = (
    "today",
    "yesterday",
    "earlier",
    "last time",
    "we talked",
    "i said",
    "i asked",
    "meeting",
    "just now",
    "idag",
    "igar",
    "igår",
    "nyss",
    "forra",
    "förra",
    "mote",
    "möte",
    "vi pratade",
    "jag sa",
)

_MY_SLOT_RE = re.compile(r"\bmy\s+(?P<slot>[a-z0-9 _-]{2,40})\s+is\s+(?P<value>.+)$", re.IGNORECASE)
_MY_SLOT_SV_RE = re.compile(
    r"\b(?:min|mitt|mina)\s+(?P<slot>[a-z0-9åäö _-]{2,40})\s+är\s+(?P<value>.+)$",
    re.IGNORECASE,
)
_PREFERENCE_RE = re.compile(r"\bi\s+(?:prefer|like|love)\s+(?P<value>.+)$", re.IGNORECASE)
_PREFERENCE_SV_RE = re.compile(r"\bjag\s+(?:föredrar|gillar|älskar)\s+(?P<value>.+)$", re.IGNORECASE)
_DEFAULT_RE = re.compile(r"\bdefault\s+(?P<slot>[a-z0-9 _-]{2,40})\s*(?:is|=)\s*(?P<value>.+)$", re.IGNORECASE)


def normalize_memory_kind(value: object, default: str = "semantic") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MEMORY_KINDS:
        return candidate
    return default


def parse_explicit_remember(question: object) -> Optional[Dict[str, Optional[str]]]:
    text = normalize_user_text(question, max_len=2400)
    if not text:
        return None
    match = _REMEMBER_RE.match(text)
    if not match:
        return None

    rest = normalize_user_text(match.group("rest") or "", max_len=2000)
    rest = rest.lstrip(": -")
    if not rest:
        return {"text": "", "memory_kind": None}

    kind_match = _KIND_RE.match(rest)
    if kind_match:
        kind = normalize_memory_kind(kind_match.group("kind"), default="semantic")
        body = normalize_user_text(kind_match.group("body"), max_len=1800)
        return {"text": body, "memory_kind": kind}
    return {"text": rest, "memory_kind": None}


def route_memory(
    text: object,
    memory_type_hint: Optional[str] = None,
    preferred_kind: Optional[str] = None,
) -> Dict[str, object]:
    value = normalize_user_text(text, max_len=4000)
    lower = value.lower()
    forced_kind = str(preferred_kind or "").strip().lower()

    if forced_kind in MEMORY_KINDS:
        memory_kind = forced_kind
        reason = "forced_kind"
        confidence = 0.95
    elif str(memory_type_hint or "").strip().lower() == "session":
        memory_kind = "episodic"
        reason = "memory_type_hint=session"
        confidence = 0.92
    else:
        procedural_score = _keyword_score(lower, _PROCEDURAL_HINTS)
        episodic_score = _keyword_score(lower, _EPISODIC_HINTS)
        if _looks_like_procedure(lower):
            procedural_score += 2
        if _looks_like_episode(lower):
            episodic_score += 2

        if procedural_score >= max(2, episodic_score + 1):
            memory_kind = "procedural"
            reason = "procedural_hints"
            confidence = 0.82
        elif episodic_score >= 2:
            memory_kind = "episodic"
            reason = "episodic_hints"
            confidence = 0.82
        else:
            memory_kind = "semantic"
            reason = "default_semantic"
            confidence = 0.70

    memory_type = "session" if memory_kind == "episodic" else "working"
    memory_slot, memory_value = _extract_slot_and_value(value)
    return {
        "memory_kind": memory_kind,
        "memory_type": memory_type,
        "confidence": confidence,
        "reason": reason,
        "memory_slot": memory_slot,
        "memory_value": memory_value,
    }


def _keyword_score(text: str, hints: tuple[str, ...]) -> int:
    return sum(1 for hint in hints if hint in text)


def _looks_like_procedure(text: str) -> bool:
    if "->" in text:
        return True
    if re.search(r"\b\d+\.\s+\w+", text):
        return True
    if re.search(r"\bif\b.+\bthen\b", text):
        return True
    if re.search(r"\bom\b.+\bs[aå]\b", text):
        return True
    return False


def _looks_like_episode(text: str) -> bool:
    if re.search(r"\b(today|yesterday|idag|ig[aå]r|nyss)\b", text):
        return True
    if re.search(r"\b(i|we|jag|vi)\s+(said|did|saw|sa|gjorde|sag)\b", text):
        return True
    return False


def _extract_slot_and_value(text: str) -> tuple[Optional[str], Optional[str]]:
    for pattern in (_MY_SLOT_RE, _MY_SLOT_SV_RE, _DEFAULT_RE):
        match = pattern.search(text)
        if not match:
            continue
        slot = _normalize_slot(match.group("slot"))
        value = _normalize_value(match.group("value"))
        if slot and value:
            return slot, value

    pref_match = _PREFERENCE_RE.search(text) or _PREFERENCE_SV_RE.search(text)
    if pref_match:
        value = _normalize_value(pref_match.group("value"))
        if value:
            return "preference", value
    return None, None


def _normalize_slot(value: object) -> Optional[str]:
    slot = normalize_user_text(value, max_len=60).lower()
    if not slot:
        return None
    slot = slot.replace("å", "a").replace("ä", "a").replace("ö", "o")
    slot = re.sub(r"[^a-z0-9]+", "_", slot).strip("_")
    if not slot:
        return None
    if len(slot) > 48:
        slot = slot[:48].rstrip("_")
    return slot or None


def _normalize_value(value: object) -> Optional[str]:
    text = normalize_user_text(value, max_len=280).strip(" \t\r\n.,;:")
    return text or None
