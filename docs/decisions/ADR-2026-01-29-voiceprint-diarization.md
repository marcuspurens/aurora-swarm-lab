# ADR 2026-01-29: Voiceprint + diarization MVP

## Status
Accepted

## Context
Vi behöver en MVP för diarization och voiceprint gallery utan avancerad ML-beroenden.

## Decision
- Diarization stub som märker segments med SPEAKER_1.
- Voiceprint enroll/match/review bygger artifacts för senare UI.
- Job chaining från transcribe -> diarize -> enroll -> match -> review.

## Consequences
- + Enkel MVP som är körbar utan extra modeller.
- - Inte riktig diarization ännu.
