# ADR 2026-01-29: Initiative scoring MVP

## Status
Accepted

## Context
Vi behöver en MVP för att ta emot initiativ, score:a dem och skapa en C-level rapport.

## Decision
- Pydantic används för att validera initiative payload.
- LLM scoring körs med strict JSON output.
- Publish sker till Snowflake tabellerna INITIATIVES och INITIATIVE_REPORTS.

## Consequences
- + Enkelt att köra via CLI och publicera centralt.
- - Ingen embeddings-baserad evidence länkas i MVP.
