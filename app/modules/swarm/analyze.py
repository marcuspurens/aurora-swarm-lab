"""Analyze evidence (stub)."""

from __future__ import annotations

from typing import List, Dict
from app.core.models import AnalyzeOutput


def analyze(question: str, evidence: List[Dict]) -> AnalyzeOutput:
    return AnalyzeOutput(claims=[], timeline=[], open_questions=["analysis stub"])
