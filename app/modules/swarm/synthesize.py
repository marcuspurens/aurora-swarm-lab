"""Synthesize an answer with citations (stub)."""

from __future__ import annotations

from typing import List, Dict
from app.core.models import SynthesizeOutput, SynthesizeCitation


def synthesize(question: str, evidence: List[Dict]) -> SynthesizeOutput:
    citations = []
    for ev in evidence[:3]:
        citations.append(SynthesizeCitation(doc_id=ev.get("doc_id", "N/A"), segment_id=ev.get("segment_id", "N/A")))
    return SynthesizeOutput(answer_text=f"[stub] {question}", citations=citations)
