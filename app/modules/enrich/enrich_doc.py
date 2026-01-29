"""Enrich document (stub)."""

from __future__ import annotations

from app.core.models import EnrichDocOutput


def enrich(text: str) -> EnrichDocOutput:
    return EnrichDocOutput(summary_short="", summary_long="", topics=[], entities=[])
