# ADR 2026-01-29: Graph publish + retrieve MVP

## Status
Accepted

## Context
Vi behöver kunna publicera GraphRAG-extraction till Snowflake och göra enkel graph retrieval.

## Decision
- Publish skriver MERGE SQL för ENTITIES/RELATIONS/CLAIMS/ONTOLOGY och kör mot Snowflake.
- Graph retrieval använder SQL mot ENTITIES/RELATIONS (ILIKE på entity name).

## Consequences
- + Enkel MVP som följer befintliga tabeller.
- - Retrieval är begränsad (ingen traversal/k-hop).
