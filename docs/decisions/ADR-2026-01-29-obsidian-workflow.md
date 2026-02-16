# ADR 2026-01-29: Obsidian workflow integration

## Status
Accepted

## Context
Vi behöver en MVP för Obsidian som UI: notes med frontmatter-kommandon ska trigga pipeline-jobs.

## Decision
- Watcher via `watchdog`.
- Frontmatter med `aurora_command` och parametrar.
- Auto-intake via frontmatter `aurora_auto: true` eller mapp `Aurora Inbox`.
- Output skrivs till `_outputs/<note>.output.md`.

## Consequences
- + Snabb och enkel UI utan webapp.
- - Kan trigga duplicerade körningar vid flera file-modify events.
