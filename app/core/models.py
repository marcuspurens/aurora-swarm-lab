"""Pydantic models for structured outputs."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class EnrichDocOutput(BaseModel):
    summary_short: str
    summary_long: str
    topics: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)


class ChunkEnrichOutput(BaseModel):
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


class InitiativeInput(BaseModel):
    initiative_id: str
    title: str
    problem_statement: str
    users_affected: str
    data_sources: List[str] = Field(default_factory=list)
    feasibility: str
    risk_compliance: str
    expected_value: str
    dependencies: List[str] = Field(default_factory=list)
    time_to_value: str
    strategic_alignment: str


class InitiativeScore(BaseModel):
    initiative_id: str
    title: str
    scores: dict
    overall_score: float
    rationale: str
    citations: List[SynthesizeCitation] = Field(default_factory=list)


class GraphEntity(BaseModel):
    entity_id: str
    name: str
    type: str
    aliases: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class GraphRelation(BaseModel):
    rel_id: str
    subj_entity_id: str
    predicate: str
    obj_entity_id: str
    doc_id: str
    segment_id: str
    confidence: float = 0.5


class GraphClaim(BaseModel):
    claim_id: str
    claim_text: str
    doc_id: str
    segment_id: str
    confidence: float = 0.5


class GraphEntitiesOutput(BaseModel):
    entities: List[GraphEntity] = Field(default_factory=list)
    claims: List[GraphClaim] = Field(default_factory=list)


class GraphRelationsOutput(BaseModel):
    relations: List[GraphRelation] = Field(default_factory=list)
