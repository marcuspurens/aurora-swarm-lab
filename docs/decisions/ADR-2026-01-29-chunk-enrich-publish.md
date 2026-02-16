# ADR 2026-01-29: Chunk/Enrich/Publish pipeline

## Status
Accepted

## Context
Vi behöver en minimal, modulär kedja från text/transkript till chunking, enrichment och Snowflake publish.

## Decision
- Chunking:
  - text: word-baserad chunking med överlapp
  - transcript: gruppera segment till max-längd chunkar
- Enrichment:
  - Ollama-output måste vara strikt JSON och valideras med Pydantic
- Publish:
  - Bygg MERGE SQL och försök köra mot Snowflake; skriv kvitto och fall tillbaka till dry-run vid fel.

## Consequences
- + Enkel MVP och tydliga artifacts.
- - Chunking är heuristisk och kan påverka retrieval-kvalitet.
- - Enrichment per chunk kan bli långsamt.
