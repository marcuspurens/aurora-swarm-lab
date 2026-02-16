# ADR 2026-01-29: Memory layer

## Status
Accepted

## Context
Vi behöver en MVP för minne som stöder working och long-term utan att lagra råa chattar.

## Decision
- Postgres `memory_items` för working/long-term items.
- Snowflake `MEMORY` för long-term publicering.
- CLI för write/recall (enkelt text-sök).

## Consequences
- + Enkel drift och tydlig separation mellan working och long-term.
- - Enkel ILIKE/LIKE-sökning utan embeddings.
