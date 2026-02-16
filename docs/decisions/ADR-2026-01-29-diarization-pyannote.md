# ADR 2026-01-29: Pyannote diarization integration

## Status
Accepted

## Context
Vi behöver riktig diarization för voice gallery, men vill behålla enkel drift.

## Decision
- Integrera pyannote.audio som optional dependency.
- Om PYANNOTE_TOKEN är satt kör vi pyannote; annars fallback till stub.
- Speaker labels mappas till transcript segments via överlapp i ms.

## Consequences
- + Riktig diarization när token finns.
- - Kräver pyannote install + HF token.
