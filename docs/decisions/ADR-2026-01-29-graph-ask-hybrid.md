# ADR 2026-01-29: Hybrid graph+text retrieval in ask

## Status
Accepted

## Context
Vi vill kombinera text-retrieval och graph-retrieval i ask-pipelinen.

## Decision
- `graph_retrieve` körs parallellt och resultat kombineras med text evidence.
- 1-hop traversal används som MVP.

## Consequences
- + Bättre täckning utan stora ändringar.
- - Evidence format är blandat (graph rows vs text snippets).
