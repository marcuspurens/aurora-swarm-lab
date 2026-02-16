# ADR 2026-01-29: Audio denoise (DeepFilterNet)

## Status
Accepted

## Context
Vi vill tvätta ljud innan transkribering för bättre kvalitet.

## Decision
- Lägga till optional audio denoise med DeepFilterNet.
- Om backend saknas faller vi tillbaka till passthrough.

## Consequences
- + Bättre transkriptkvalitet när backend finns.
- - Kräver extern installation av DeepFilterNet.
