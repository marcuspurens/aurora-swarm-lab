# ADR 2026-01-29: Doc extraction + YouTube audio tools

## Status
Accepted

## Context
Vi behöver en enkel, lokal MVP för dokument- och YouTube-ingest utan att bygga egna parsers.

## Decision
- Dokument: använd `python-docx` för DOCX och `pypdfium2` för PDF.
- YouTube: använd `yt-dlp` med ffmpeg-postprocessor för att extrahera m4a.

## Consequences
- + Snabbt att komma igång med etablerade verktyg.
- - PDF-extraktion kan vara låg kvalitet för komplexa PDF:er.
- - Enqueue-youtube kräver nedladdning för att beräkna `source_version`.
