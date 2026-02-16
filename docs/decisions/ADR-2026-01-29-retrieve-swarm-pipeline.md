# ADR 2026-01-29: Retrieval + Swarm pipeline

## Status
Accepted

## Context
Vi behöver en enkel MVP för retrieval och ask-pipeline som är kompatibel med Snowflake och lokala modeller.

## Decision
- Retrieval:
  - SQL mot KB_SEGMENTS + DOCUMENTS med ILIKE på TEXT.
  - Filter stöd: topics/entities/source_type/date range.
- Swarm pipeline:
  - route (fast model) -> retrieve -> analyze (strong vid behov) -> synthesize.
  - LLM-output måste vara strikt JSON och valideras med Pydantic.

## Consequences
- + Enkel pipeline med tydliga steg och minimalt schema-beroende.
- - ILIKE-baserad retrieval ger låg precision utan embeddings.
