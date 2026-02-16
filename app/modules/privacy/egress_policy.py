"""Optional PII egress policy for outbound LLM prompts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List

from app.core.config import Settings, load_settings

_EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s().-]*)?(?:\d[\s().-]*){7,14}\d(?!\w)")
_IPV4_RE = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_SE_PERSONNUMMER_RE = re.compile(r"(?<!\d)(?:\d{6}[-+]?\d{4}|\d{8}[-+]?\d{4})(?!\d)")

_SUPPORTED_MODES = {"off", "pseudonymize", "redact"}
_SUPPORTED_PROVIDERS = {"ollama", "chatgpt"}


@dataclass(frozen=True)
class EgressPolicyDecision:
    provider: str
    configured_mode: str
    effective_mode: str
    text: str
    reason_codes: List[str]
    transformed: bool
    transform_count: int


def apply_egress_policy(text: str, provider: str) -> EgressPolicyDecision:
    settings = load_settings()
    normalized_provider = _normalize_provider(provider)
    configured_mode = _normalize_mode(settings.egress_pii_policy)
    raw = str(text or "")

    if not _provider_enabled(settings, normalized_provider):
        return EgressPolicyDecision(
            provider=normalized_provider,
            configured_mode=configured_mode,
            effective_mode="off",
            text=raw,
            reason_codes=[f"allow.provider_filter_disabled.{normalized_provider}"],
            transformed=False,
            transform_count=0,
        )

    if configured_mode == "off":
        return EgressPolicyDecision(
            provider=normalized_provider,
            configured_mode=configured_mode,
            effective_mode="off",
            text=raw,
            reason_codes=["allow.egress_policy_off"],
            transformed=False,
            transform_count=0,
        )

    transformed = raw
    total_count = 0
    reason_codes: List[str] = []
    replacements: dict[str, str] = {}
    patterns = [
        ("email", _EMAIL_RE),
        ("se_personnummer", _SE_PERSONNUMMER_RE),
        ("phone", _PHONE_RE),
        ("ip_address", _IPV4_RE),
    ]

    for category, pattern in patterns:
        transformed, count = _replace_matches(
            transformed,
            pattern,
            category=category,
            mode=configured_mode,
            salt=settings.egress_pii_token_salt,
            replacements=replacements,
        )
        if count > 0:
            action = "pseudonymize" if configured_mode == "pseudonymize" else "redact"
            reason_codes.append(f"transform.{action}.{category}")
            total_count += count

    if total_count == 0:
        reason_codes.append("allow.no_pii_detected")

    return EgressPolicyDecision(
        provider=normalized_provider,
        configured_mode=configured_mode,
        effective_mode=configured_mode,
        text=transformed,
        reason_codes=reason_codes,
        transformed=transformed != raw,
        transform_count=total_count,
    )


def _replace_matches(
    text: str,
    pattern: re.Pattern[str],
    category: str,
    mode: str,
    salt: str,
    replacements: dict[str, str],
) -> tuple[str, int]:
    count = 0

    def _sub(match: re.Match[str]) -> str:
        nonlocal count
        value = match.group(0)
        if not value:
            return value
        replacement = replacements.get(value)
        if replacement is None:
            if mode == "pseudonymize":
                replacement = _stable_token(category=category, value=value, salt=salt)
            else:
                replacement = f"[REDACTED_{category.upper()}]"
            replacements[value] = replacement
        count += 1
        return replacement

    return pattern.sub(_sub, text), count


def _stable_token(category: str, value: str, salt: str) -> str:
    raw = f"{salt}|{category}|{value}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"[PII_{category.upper()}_{digest}]"


def _normalize_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode in _SUPPORTED_MODES:
        return mode
    return "off"


def _normalize_provider(value: str) -> str:
    provider = str(value or "").strip().lower()
    if provider in _SUPPORTED_PROVIDERS:
        return provider
    return "ollama"


def _provider_enabled(settings: Settings, provider: str) -> bool:
    if provider == "chatgpt":
        return bool(getattr(settings, "egress_pii_apply_to_chatgpt", True))
    return bool(getattr(settings, "egress_pii_apply_to_ollama", True))
