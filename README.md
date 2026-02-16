# aurora-swarm-lab

## Avsiktsforklaring
Bygger en lokal, modular AI-assistent pa Mac som kan koras och vaxa over tid.

Ingestar dokument, URL:er och YouTube/ljudfiler och gor allt sokbart.

Transkriberar ljud via Whisper och sparar segment med tidskoder som kan citeras.

Chunksar och berikar innehall med metadata (sammanfattning, amnen, entiteter).

Publicerar allt till en dedikerad Snowflake-databas som fungerar som Knowledge Base.

Kor en agent-swarm som routar fragor, hamtar evidens och genererar svar med kallhanvisningar.

Har stod for minne (kort-, mellan- och langtidsminne) samt arbetsfloden via Obsidian.

Ar forberett for GraphRAG/ontologi (EBUCore+) och senare MCP/MCP Apps-UI (t.ex. voiceprint gallery).

---

## Snabbstart (Phase A)
1) Skapa .env
```
cp .env.example .env
```
2) Bootstrap Postgres
```
python -m app.cli.main bootstrap-postgres
```
3) Kolla status
```
python -m app.cli.main status
```

## Phase B (P1-5): Ingest URL (MVP)
1) Enqueue URL
```
python -m app.cli.main enqueue-url <url>
```
2) Starta worker (io-lane)
```
python -m app.cli.main worker --lane io
```
Artifacts hamnar under `data/artifacts/<safe_source_id>/<source_version>/`.

## Phase B (P1-6): Ingest PDF/DOCX (MVP)
1) Enqueue dokument
```
python -m app.cli.main enqueue-doc <path>
```
2) Starta worker (io-lane)
```
python -m app.cli.main worker --lane io
```

## Phase B (P1-7/8): YouTube/audio + Whisper transcription (MVP)
1) Enqueue YouTube
```
python -m app.cli.main enqueue-youtube <url>
```
2) Starta workers
```
python -m app.cli.main worker --lane io
python -m app.cli.main worker --lane transcribe
```
Transcribe-backend väljs via `.env`:
- `TRANSCRIBE_BACKEND=auto` (default, försöker `whisper` CLI först och fallbackar till `faster_whisper`)
- `TRANSCRIBE_BACKEND=whisper_cli` (kräver `whisper` i PATH)
- `TRANSCRIBE_BACKEND=faster_whisper` (kräver Python-paketet `faster-whisper`)

## Phase B (P1-9/10/11): Chunking + Enrichment + Publish (MVP)
1) Starta workers
```
python -m app.cli.main worker --lane oss20b
python -m app.cli.main worker --lane io
```
Chunking + enrichment körs automatiskt efter ingest/transcribe och publicering körs efter enrich.

## Phase C (P2-12/13): Retrieval + Ask pipeline (MVP)
1) Starta worker (vid behov för ingest/publish)
```
python -m app.cli.main worker --lane oss20b
python -m app.cli.main worker --lane io
```
2) Ställ en fråga
```
python -m app.cli.main ask "<question>"
python -m app.cli.main ask "<question>" --user-id user-1 --project-id aurora --session-id chat-42
```
Swarm-flödet har fallback om modelltjänsten fallerar tillfälligt (route/analyze/synthesize), och Ollama-anrop kör retry/backoff via:
`OLLAMA_REQUEST_TIMEOUT_SECONDS`, `OLLAMA_REQUEST_RETRIES`, `OLLAMA_REQUEST_BACKOFF_SECONDS`.
Input till `ask` normaliseras också (trim + whitespace-normalisering + maxlängd), och tom fråga avvisas.
Route-output saneras dessutom innan retrieval (whitelistade filter + clamp av `retrieve_top_k`).
`run_log` skyddas mot stora payloads via `RUN_LOG_MAX_JSON_CHARS` och `RUN_LOG_MAX_ERROR_CHARS`.

## Phase D (P3-14): Memory (MVP)
1) Skriv minne
```
python -m app.cli.main memory-write --type working --text "Kom ihåg detta"
python -m app.cli.main memory-write --type working --text "Scoped note" --user-id user-1 --project-id aurora --session-id chat-42
```
Exempel med policyfält:
```
python -m app.cli.main memory-write --type working --text "Viktigt" --importance 0.9 --confidence 0.8 --expires-at 2026-12-31T23:59:59+00:00
```
2) Hämta minne
```
python -m app.cli.main memory-recall --query "Kom ihåg" --type working --limit 5
python -m app.cli.main memory-recall --query "Scoped note" --type working --user-id user-1 --project-id aurora --session-id chat-42
```
3) Visa memory-observability
```
python -m app.cli.main memory-stats
python -m app.cli.main memory-stats --user-id user-1 --project-id aurora --session-id chat-42
```
Memory retrieval rankas nu med textmatch, recency och policyfält (importance/confidence/access/expiry/pin).
Ask-flödet checkpointar nu också automatiskt turns till session-minne och skriver en löpande handoff i `data/artifacts/context/auto_handoff.md`.
För ny chatt-resume kan du skicka `--session-id` i CLI (eller `session_id` i MCP `ask`) så injiceras senaste `auto_handoff` automatiskt på första turn i sessionen.
Bakgrunds-checkpoint i MCP-servern styrs via `CONTEXT_HANDOFF_BACKGROUND_INTERVAL_SECONDS` (sekunder, default 300).
Count-baserad pre-compaction av session-turns styrs via `CONTEXT_HANDOFF_PRE_COMPACTION_TURN_COUNT` (default 12).
`ask` stöder nu explicit minnes-hook: fraser som `remember this: ...` eller `kom ihåg detta: ...` routeas till `memory_kind` (`semantic/episodic/procedural`) och kan superseda motsägande minnen.
Consolidation/supersede skriver nu även revision trail med `supersedes`/`superseded_by`, `supersede_reason_code` och `revision_timeline`.
Retrospective retrieval feedback-loop är aktiv: efter `ask` skrivs feedback-minnen baserat på evidence + citations, och nästa retrieval använder dessa för lätt reranking. Styrs via `RETRIEVAL_FEEDBACK_*` i `.env`.
Feedback-loop stöder nu även decay/aging (`RETRIEVAL_FEEDBACK_DECAY_HALF_LIFE_HOURS`) och cap per query-cluster (`RETRIEVAL_FEEDBACK_CLUSTER_CAP`) för att minska överanpassning.
Scope-isolering stöds nu förstaklassigt för memory read/write/retrieve med `user_id`, `project_id`, `session_id` (CLI + MCP).

Visa senaste auto-handoff:
```
python -m app.cli.main context-handoff
```

## Phase D (P3-15): Obsidian workflow (MVP)
1) Sätt `OBSIDIAN_VAULT_PATH` i `.env`
2) Starta watcher
```
python -m app.cli.main obsidian-watch
```
3) Skapa en note med frontmatter:
```
---
aurora_command: ingest_url
url: https://example.com
---
```
Output skrivs till `_outputs/<note>.output.md`.

## Phase E (P4-16/17): Initiative scoring + reports (MVP)
1) Skapa en JSON-fil med initiativ:
```
[
  {
    "initiative_id": "init_1",
    "title": "AI onboarding",
    "problem_statement": "Onboarding tar för lång tid.",
    "users_affected": "Nya anställda",
    "data_sources": ["HR-notes"],
    "feasibility": "Medium",
    "risk_compliance": "Low",
    "expected_value": "Time saved",
    "dependencies": ["HR system"],
    "time_to_value": "3 months",
    "strategic_alignment": "High"
  }
]
```
2) Kör scoring:
```
python -m app.cli.main score-initiatives --input ./initiatives.json
```

## Phase F (P5): GraphRAG extraction (MVP)
1) Starta workers
```
python -m app.cli.main worker --lane nemotron
python -m app.cli.main worker --lane oss20b
```
Graph-extraktion körs efter enrichment och skriver `graph/entities.jsonl`, `graph/relations.jsonl`, `graph/claims.jsonl`, `graph/ontology.json`.
Publish till Snowflake körs efter relations och skriver `graph/publish_receipt.json`.

## Phase F (P5): Graph retrieval (MVP)
```
python -m app.cli.main ask "<question>"
```
Graph retrieval används nu av ask-pipen och gör en enkel 1-hop lookup mot graph-tabellerna.

## Phase F (P5): Embeddings retrieval (MVP)
- Kräver Ollama embeddings modell (default `nomic-embed-text`).
- Sätt `EMBEDDINGS_ENABLED=1` och ev. `OLLAMA_MODEL_EMBED=...` i `.env`.
- Embeddings byggs per chunk och används före keyword-sök.

## Phase G (P6): MCP server (MVP)
Starta MCP-server över stdio:
```
python -m app.cli.main mcp-server
```
Tools: ingest_url, ingest_doc, ingest_youtube, ask, memory_write, memory_recall, memory_stats, status.
`ask`, `memory_write`, `memory_recall` och `memory_stats` accepterar även `user_id`, `project_id`, `session_id` för scope-isolering.

## Phase G (P6): Voice Gallery MCP UI (MVP)
1) Starta MCP-server:
```
python -m app.cli.main mcp-server
```
2) Öppna UI-resursen `ui://voice-gallery` via MCP-klienten.
3) Redigera EBUCore+ fält via tool `voice_gallery_update`.
4) Voice Gallery metadata indexeras för embeddings + GraphRAG automatiskt.

## Phase G (P6): Intake MCP UI (MVP)
1) Starta MCP-server:
```
python -m app.cli.main mcp-server
```
2) Öppna UI-resursen `ui://intake` via MCP-klienten.
3) Klistra in länkar och klicka "Enqueue ingest".

## Phase G (P6): Obsidian auto-intake (MVP)
1) Sätt `OBSIDIAN_VAULT_PATH` i `.env`.
2) Skapa mappen `Aurora Inbox` i din vault.
3) Starta watcher:
```
python -m app.cli.main obsidian-watch
```
4) Klistra in URLs eller filvägar i en note i `Aurora Inbox`.
   - Om noten bara innehåller text enqueues den som dokument.
   - Output skrivs till `_outputs/<note>.output.md`.

### Auto-start (macOS)
- LaunchAgent: `~/Library/LaunchAgents/com.aurora.obsidian-watch.plist`
- Script: `scripts/obsidian_watch.sh`
- Logs: `~/Library/Logs/aurora-obsidian-watch.log`

### Workers auto-start (macOS)
- LaunchAgent: `~/Library/LaunchAgents/com.aurora.workers.plist`
- Script: `scripts/aurora_workers.sh`
- Logs: `~/Library/Logs/aurora-workers.log`

## Phase G (P6): Voiceprint + diarization (MVP)
1) Starta workers
```
python -m app.cli.main worker --lane transcribe
python -m app.cli.main worker --lane nemotron
```
2) Ingesta YouTube eller ljudfil så att transcribe körs.
Artifacts skapas i:
- `transcript/segments_diarized.jsonl`
- `voiceprint/voiceprints.jsonl`
- `voiceprint/matches.jsonl`
- `voiceprint/review.json`
3) För riktig diarization: installera `pyannote.audio` och sätt `PYANNOTE_TOKEN` i `.env`.
4) För audio denoise (DeepFilterNet): installera verktyget och sätt:
```
AUDIO_DENOISE_ENABLED=1
AUDIO_DENOISE_BACKEND=deepfilternet
DEEPFILTERNET_CMD=deepfilternet
```
5) För transkribering kan du välja backend:
```
TRANSCRIBE_BACKEND=auto
WHISPER_MODEL=small
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=default
```

## CLI
```
python -m app.cli.main bootstrap-postgres
python -m app.cli.main bootstrap-snowflake
python -m app.cli.main enqueue-url <url>
python -m app.cli.main enqueue-doc <path>
python -m app.cli.main enqueue-youtube <url>
python -m app.cli.main worker --lane oss20b
python -m app.cli.main worker --lane nemotron
python -m app.cli.main worker --lane transcribe
python -m app.cli.main status
python -m app.cli.main ask "<question>"
```

## Struktur
- `app/core/` config, ids, manifest, storage, models
- `app/queue/` Postgres queue + run logs
- `app/clients/` clients (snowflake, ollama, whisper)
- `app/modules/` moduler (intake, transcribe, enrich, publish)
- `app/cli/` CLI
- `scripts/` bootstrap & worker helpers
- `tests/` minimum tests

## Status
Phase A scaffolding klar: queue, manifest, artifacts, Snowflake bootstrap, CLI.
