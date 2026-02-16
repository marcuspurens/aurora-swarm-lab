# ADR 2026-01-29: Voice Gallery MCP UI

## Status
Accepted

## Context
Vi behöver en redigerbar Voice Gallery för EBUCore+ metadata.

## Decision
- Voice Gallery lagras lokalt i `voice_gallery.json`.
- MCP tools för list/update.
- MCP UI resource `ui://voice-gallery` (minimal scaffold).
- EBUCore+ fält: utökad, men inte full strikt schema (lagras som JSON).

## Consequences
- + Snabbt att editera metadata.
- - UI är minimal; mer UI kräver MCP Apps senare.
