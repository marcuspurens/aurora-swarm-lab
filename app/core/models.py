"""Pydantic models for structured outputs."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EnrichDocOutput(BaseModel):
    summary_short: str
    summary_long: str
    topics: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)


class RouteOutput(BaseModel):
    intent: str
    filters: dict = Field(default_factory=dict)
    retrieve_top_k: int = 10
    need_strong_model: bool = False
    reason: Optional[str] = None


class AnalyzeOutput(BaseModel):
    claims: List[str] = Field(default_factory=list)
    timeline: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)


class SynthesizeCitation(BaseModel):
    doc_id: str
    segment_id: str
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


class SynthesizeOutput(BaseModel):
    answer_text: str
    citations: List[SynthesizeCitation] = Field(default_factory=list)
