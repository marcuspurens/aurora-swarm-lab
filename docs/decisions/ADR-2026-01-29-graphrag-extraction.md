# ADR 2026-01-29: GraphRAG extraction MVP

## Status
Accepted

## Context
Vi behöver en minimal GraphRAG-extraction för entities/relations/claims utan UI.

## Decision
- LLM-extraction med strict JSON (Pydantic) från enriched chunks.
- Artifacts skrivs i `graph/` och används senare för grafpublishing/retrieval.
- Relation extraction körs efter entity extraction.

## Consequences
- + Enkel MVP med tydliga artifacts.
- - Kör på chunk-sample (max 20) och kan missa long-tail entities.
