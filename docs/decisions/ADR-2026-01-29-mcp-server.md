# ADR 2026-01-29: MCP server MVP

## Status
Accepted

## Context
Vi behöver en MCP-brygga så externa klienter kan anropa ingest/ask/memory.

## Decision
- Implementera minimal JSON-RPC över stdio (`tools/list`, `tools/call`).
- Exponera tools: ingest_url, ingest_doc, ingest_youtube, ask, memory_write, memory_recall, status.

## Consequences
- + Enkel att koppla mot klienter som stöder stdio.
- - Inte full MCP Apps UI ännu.
