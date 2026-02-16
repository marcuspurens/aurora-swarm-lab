# ADR 2026-01-29: Readable text extraction via html.parser

## Status
Accepted

## Context
Vi behöver en minimal och dependency-fri MVP för att extrahera läsbar text ur HTML i URL-ingest.

## Decision
Använd Python stdlib `html.parser` med enkla block-tag heuristiker och skip av script/style/noscript.

## Consequences
- + Inga extra dependencies, enkel drift.
- - Heuristisk och kan missa/inkludera felaktigt innehåll på komplexa sidor.
