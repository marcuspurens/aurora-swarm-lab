"""Memory policy helpers for write/read behavior and ranking."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional


TYPE_WEIGHT = {
    "session": 1.0,
    "working": 0.9,
    "long_term": 0.8,
}

DEFAULT_TTL_DAYS = {
    "session": 1,
    "working": 30,
    "long_term": None,
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def parse_iso(value: Optional[object]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def clamp_float(value: Optional[object], default: float, low: float = 0.0, high: float = 1.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        numeric = default
    return max(low, min(high, numeric))


def normalize_memory_type(memory_type: object) -> str:
    candidate = str(memory_type or "working").strip().lower()
    if candidate in TYPE_WEIGHT:
        return candidate
    return "working"


def normalize_list(values: Optional[Iterable[object]]) -> List[str]:
    out: List[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text:
            continue
        if text not in out:
            out.append(text)
    return out


def normalize_text(text: object, max_len: int = 8000) -> str:
    value = str(text or "").strip()
    if len(value) <= max_len:
        return value
    return value[:max_len].rstrip()


def default_expiry(memory_type: str, created_at: datetime) -> Optional[str]:
    ttl_days = DEFAULT_TTL_DAYS.get(memory_type)
    if ttl_days is None:
        return None
    return (created_at + timedelta(days=ttl_days)).isoformat()


_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokens(text: object) -> List[str]:
    return _TOKEN_RE.findall(str(text or "").lower())


def overlap_score(query_tokens: List[str], text: object) -> float:
    if not query_tokens:
        return 0.0
    haystack = set(tokens(text))
    if not haystack:
        return 0.0
    hits = sum(1 for t in query_tokens if t in haystack)
    return hits / len(query_tokens)


def recency_score(created_at: Optional[object], half_life_days: float = 14.0) -> float:
    created_dt = parse_iso(created_at)
    if created_dt is None:
        return 0.3
    age_days = max(0.0, (now_utc() - created_dt).total_seconds() / 86400.0)
    return 1.0 / (1.0 + (age_days / half_life_days))
