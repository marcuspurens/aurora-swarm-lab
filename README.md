# aurora-swarm-lab

## Project Standards
- License: `LICENSE`
- Contributing guide: `CONTRIBUTING.md`
- Security policy: `SECURITY.md`
- Code of conduct: `CODE_OF_CONDUCT.md`
- Changelog: `CHANGELOG.md`

## Avsiktsforklaring
Bygger en lokal, modular AI-assistent pa Mac som kan koras och vaxa over tid.

Ingestar dokument, URL:er och YouTube/ljudfiler och gor allt sokbart.

Transkriberar ljud via Whisper och sparar segment med tidskoder som kan citeras.

Chunksar och berikar innehall med metadata (sammanfattning, amnen, entiteter).

Promptar ligger som textmallar i `app/prompts/` (inte hardkodade i Python-moduler).

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
URL-ingest kör snabb HTTP-scrape först och kan fallbacka till headless rendering för JS-tunga sidor när texten blir tunn.
Styrning via `.env`:
`AURORA_URL_HEADLESS_FALLBACK_ENABLED`,
`AURORA_URL_HEADLESS_FALLBACK_MIN_TEXT_CHARS`,
`AURORA_URL_HEADLESS_TIMEOUT_MS`,
`AURORA_URL_HEADLESS_WAIT_UNTIL`,
`AURORA_URL_HEADLESS_BROWSER`.
För fallback krävs `playwright` + browser binaries installerade lokalt.

Skalning för mycket data:
- Behåll allt source-lokalt i `data/artifacts/<source>/<version>/...` (nuvarande default) för dedupe/spårbarhet.
- Exportera endast sammanfattningar (`transcript/summary.md`) till Obsidian/sekundärt lager om du vill minska brus.
- Kör retention/arkivering av äldre `source_version`-mappar när lagring växer.

## Phase B (P1-6): Ingest PDF/DOCX (MVP)
1) Enqueue dokument
```
python -m app.cli.main enqueue-doc <path>
```
2) Starta worker (io-lane)
```
python -m app.cli.main worker --lane io
```
PDF-ingest laster text-layer med `pypdfium2` och kan fallbacka till OCR for scannade PDF:er
nar texten ar tunn. OCR styrs via `.env`:
`AURORA_DOC_OCR_ENABLED`,
`AURORA_DOC_OCR_BACKEND` (`auto|paddleocr|tesseract`, `auto` provar PaddleOCR forst),
`AURORA_DOC_OCR_MIN_TEXT_CHARS`,
`AURORA_DOC_OCR_LANG`,
`AURORA_DOC_OCR_PADDLE_LANG`,
`AURORA_DOC_OCR_RENDER_SCALE`,
`AURORA_DOC_OCR_MAX_PAGES`.
For OCR behovs minst ett backend:
- PaddleOCR: Python-paketet `paddleocr` (och dess beroenden)
- Tesseract: `tesseract` (binar) + Python-paketet `pytesseract`
Tips for PaddleOCR i mer stangda miljoer: satt `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`.

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
Alternativt: `./scripts/aurora_workers.sh` valjer automatiskt en Python-miljo som har transcribe-backend tillganglig (`whisper` CLI eller `faster_whisper`).
Transcribe-backend väljs via `.env`:
- `TRANSCRIBE_BACKEND=auto` (default, försöker `whisper` CLI först och fallbackar till `faster_whisper`)
- `TRANSCRIBE_BACKEND=whisper_cli` (kräver `whisper` i PATH)
- `TRANSCRIBE_BACKEND=faster_whisper` (kräver Python-paketet `faster-whisper`)
- Efter transcribe körs även `transcript_markdown` som skriver:
  - `transcript/summary.json` (renskriven text + sammanfattning)
  - `transcript/summary.md` (läsbar markdown)
- Promptstorlek styrs via `AURORA_TRANSCRIPT_MARKDOWN_MAX_CHARS` (default `24000`).

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
Om scope saknas i kommandot används default från `.env` (om satta):
`AURORA_DEFAULT_USER_ID`, `AURORA_DEFAULT_PROJECT_ID`, `AURORA_DEFAULT_SESSION_ID`.
Swarm-flödet har fallback om modelltjänsten fallerar tillfälligt (route/analyze/synthesize), och Ollama-anrop kör retry/backoff via:
`OLLAMA_REQUEST_TIMEOUT_SECONDS`, `OLLAMA_REQUEST_RETRIES`, `OLLAMA_REQUEST_BACKOFF_SECONDS`.
Input till `ask` normaliseras också (trim + whitespace-normalisering + maxlängd), och tom fråga avvisas.
Route-output saneras dessutom innan retrieval (whitelistade filter + clamp av `retrieve_top_k`).
`run_log` skyddas mot stora payloads via `RUN_LOG_MAX_JSON_CHARS` och `RUN_LOG_MAX_ERROR_CHARS`.
Valbart outbound PII-filter för LLM-prompts styrs via:
`EGRESS_PII_POLICY=off|pseudonymize|redact` (default `redact`),
`EGRESS_PII_FAIL_CLOSED` (default `1`, invalid mode fallbackar till `redact`),
`EGRESS_PII_APPLY_TO_OLLAMA`,
`EGRESS_PII_APPLY_TO_CHATGPT`,
`EGRESS_PII_TOKEN_SALT` (för stabil pseudonymiseringstoken).
`run_log` för route/analyze/synthesize innehåller audit-fält som `egress_policy_provider`, `egress_policy_mode`, `egress_policy_reason_codes`, `egress_policy_fail_closed`, `egress_policy_input_chars`, `egress_policy_output_chars`.
Local file-ingest kör allowlist: sätt `AURORA_INGEST_PATH_ALLOWLIST` (kommaseparerade paths) och styr enforcement med `AURORA_INGEST_PATH_ALLOWLIST_ENFORCED`.
`ingest_auto` stödjer nu även mappar (rekursivt) och begränsas av `AURORA_INGEST_AUTO_MAX_FILES_PER_DIR` (default `500`).
`ingest_auto` stödjer även strukturerad källmetadata:
`tags`, `context`, `speaker`, `organization`, `event_date` (YYYY-MM-DD) och `source_metadata` (objekt).
Metadata sparas i manifest under `metadata.intake.source_metadata` och speglas i `metadata.ebucore_plus`.

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
4) Kör memory-maintenance (lifecycle hygiene)
```
python -m app.cli.main memory-maintain
python -m app.cli.main memory-maintain --user-id user-1 --project-id aurora --session-id chat-42
python -m app.cli.main memory-maintain --enqueue
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
Graph publish kör nu ontologi-validering (predicate + domain/range) fail-closed:
ogiltiga relationer blockeras från publish och skrivs till `graph/validation_report.json`.
Relations-extraktion kan begränsa promptstorlek med `AURORA_GRAPH_RELATIONS_MAX_CHUNKS` (default `20`) för att minska timeout-risk.

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
Tools: ingest_url, ingest_doc, ingest_youtube, ask, memory_write, memory_recall, memory_stats, memory_maintain, status, dashboard_stats, dashboard_timeseries, dashboard_alerts, dashboard_models, ingest_auto, intake_open, obsidian_watch_status, obsidian_list_notes, obsidian_enqueue_note, dashboard_open.
`ingest_auto` accepterar: `text`, `items`, `dedupe`, `tags`, `context`, `speaker`, `organization`, `event_date`, `source_metadata`.
`ask`, `memory_write`, `memory_recall`, `memory_stats` och `memory_maintain` accepterar även `user_id`, `project_id`, `session_id` för scope-isolering.
Om scope saknas i MCP-arguments används samma `.env` defaults (`AURORA_DEFAULT_*`).
När `MCP_REQUIRE_EXPLICIT_INTENT=1` (default) kräver side-effect actions explicit `intent`:
`ask` med remember-flöde -> `intent=remember`, `memory_write` TODO -> `intent=todo`, övrig `memory_write` -> `intent=write`.
Valbar tool allowlist per klient/use-case:
`MCP_TOOL_ALLOWLIST=*|tool1,tool2` och `MCP_TOOL_ALLOWLIST_BY_CLIENT="codex=ask,memory_recall;codex/intake=ingest_auto,ask,memory_write;@mobile=ask,memory_write"`.

## Codex Desktop as UI
Codex Desktop kan vara ditt primära UI mot Aurora via MCP.

1) Registrera Aurora MCP-server i Codex:
```
codex mcp add aurora -- /Users/mpmac/aurora-swarm-lab/scripts/aurora_mcp_server.sh
```
2) Verifiera:
```
codex mcp list
codex mcp get aurora --json
```
3) Starta om Codex Desktop.
4) Använd Aurora-tools i Codex (`ask`, `memory_write`, `memory_recall`, `memory_stats`), eller öppna MCP-resurserna `ui://intake` / `ui://dashboard`.

Helper-script för Codex MCP-start finns i:
`scripts/aurora_mcp_server.sh`

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
3) Klistra in länkar/filsökvägar, eller drag-and-drop filer från Finder.
4) Klicka "Ingest (auto)".
UI:t har även snabbknappar med förklaring:
`Importera`, `Fraga`, `Kom ihag`, `TODO`.
För dashboard som egen UI-resurs, öppna:
`ui://dashboard` (eller tool `dashboard_open`).
Dashboarden visar:
`Overview` (mål/progress), `Pipeline` (24h timeseries), `Alerts` (driftvarningar), `Models` (modell/tokens-estimat).

### Intake UI i vanlig webbläsare (med fungerande knappar)
Om din klient bara visar `ui://intake` som text/HTML, kör lokal webserver:
```
scripts/intake_ui_server.sh
```
Öppna sedan:
```
http://127.0.0.1:8765
```
Knapparna proxar då lokalt till Aurora tools via `/api/tools/call`.

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
- One-shot install: `scripts/install_autostart_mac.sh`
- One-shot uninstall: `scripts/uninstall_autostart_mac.sh`
- Installer skapar LaunchAgents:
  - `com.aurora.workers` (workers)
  - `com.aurora.intake-ui` (`http://127.0.0.1:8765`)
  - `com.aurora.obsidian-watch` (om `OBSIDIAN_VAULT_PATH` finns)
  - `com.aurora.dropbox-watch` (om `AURORA_DROPBOX_PATHS` finns)
- Logs: `~/Library/Logs/aurora-*.log`
- Restarta alla Aurora-agenter:
```
UID_NOW=$(id -u)
launchctl kickstart -k gui/${UID_NOW}/com.aurora.workers
launchctl kickstart -k gui/${UID_NOW}/com.aurora.intake-ui
launchctl kickstart -k gui/${UID_NOW}/com.aurora.obsidian-watch
launchctl kickstart -k gui/${UID_NOW}/com.aurora.dropbox-watch
```

## Hands-free intake (drag/drop/copy-paste/folder watch)
Sätt i `.env`:
```
OBSIDIAN_VAULT_PATH=/absolute/path/to/your/vault
AURORA_DROPBOX_PATHS=/absolute/path/to/AuroraDrop,/absolute/path/to/MoreDropFolders
AURORA_DROPBOX_RECURSIVE=1
AURORA_DROPBOX_SCAN_ON_START=1
AURORA_DROPBOX_DEBOUNCE_SECONDS=1.2
```
Flöde:
- Släpp filer i dropbox-mapp(ar) eller i Obsidian note.
- Watchers enqueuar ingest automatiskt.
- Workers indexerar, chunkar, vektoriserar och fortsätter pipeline automatiskt.

## Mobile-first usage (iPhone/Android)
Snabbaste stabila vägen är mobil -> SSH -> Aurora CLI.

1) Se till att maskinen där Aurora kör är nåbar från mobilen (t.ex. Tailscale + SSH).
2) Använd wrappern:
```
scripts/mobile_aurora.sh ask "Vad är planen idag?"
scripts/mobile_aurora.sh remember "Jag intervjuar Anna kl 14"
scripts/mobile_aurora.sh todo-add "Skicka följdfrågor till redaktionen"
scripts/mobile_aurora.sh todo-list
```
3) Sätt gärna mobil-scope i `.env`:
```
AURORA_MOBILE_USER_ID=marcus
AURORA_MOBILE_PROJECT_ID=journal
AURORA_MOBILE_SESSION_ID=mobile-chat
AURORA_MOBILE_TODO_LIMIT=12
```

För röst på mobilen: använd diktat i tangentbordet (eller iOS Shortcuts "Dictate Text") och skicka texten till `scripts/mobile_aurora.sh`.

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
