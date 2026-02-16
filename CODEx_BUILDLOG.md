# CODEx Build Log

## 2026-01-29
- Mål/fas: Phase B (P1-5) Ingest URL (scrape -> canonical text).
- Byggt:
  - URL-scrape via minimal HTTP-klient.
  - Readable text-extraktion (HTMLParser) + normalisering.
  - URL-ingest modul som sparar artifacts och uppdaterar manifest.
  - CLI: enqueue-url beräknar source_version från canonical text; worker hanterar ingest_url.
  - Tester för readable text och ingest-url artifacts/manifest.
- Kör lokalt:
  - `python -m app.cli.main enqueue-url <url>`
  - `python -m app.cli.main worker --lane io`
- Kända problem:
  - Readable text är heuristisk och kan missa innehåll på komplexa sidor.
  - Enqueue-url gör en nätverksfetch för att beräkna source_version.

## 2026-01-29 (P1-6/7/8)
- Mål/fas: Phase B forts. (P1-6/7/8) ingest doc + YouTube/audio + Whisper transcription.
- Byggt:
  - Doc-extraktion för TXT/DOCX/PDF.
  - Doc-ingest som sparar raw+canonical text och uppdaterar manifest.
  - YouTube audio-extract via yt-dlp (m4a) och transcribe-job enqueue.
  - Whisper transcription: SRT + segments.jsonl och manifest uppdatering.
  - CLI/worker wiring för ingest_doc, ingest_youtube, transcribe_whisper.
  - Tester för doc extract, YouTube ingest och transcribe-modul.
- Kör lokalt:
  - `python -m app.cli.main enqueue-doc <path>`
  - `python -m app.cli.main enqueue-youtube <url>`
  - `python -m app.cli.main worker --lane io`
  - `python -m app.cli.main worker --lane transcribe`
- Kända problem:
  - YouTube enqueue gör en nedladdning för att beräkna source_version.
  - PDF-extraktion är enkel och kan ge låg kvalitet på komplexa PDF:er.

## 2026-01-29 (P1-9/10/11)
- Mål/fas: Phase B forts. (P1-9/10/11) chunking + enrichment + Snowflake publish.
- Byggt:
  - Chunking för text och transkript till `chunks/chunks.jsonl`.
  - Enrichment via Ollama (strict JSON + Pydantic) för doc och chunks.
  - Publish till Snowflake med kvitto `publish/snowflake_receipt.json` (dry-run vid fel).
  - Orkestrering: chunk/enrich/publish jobkedja.
  - Tester för chunking, enrich, publish.
- Kör lokalt:
  - `python -m app.cli.main worker --lane oss20b`
  - `python -m app.cli.main worker --lane io`
- Kända problem:
  - Snowflake connector saknas i pip-listan; publish kan falla och blir dry-run.
  - Enrichment är per-chunk och kan vara långsamt.

## 2026-01-29 (P2-12/13)
- Mål/fas: Phase C (P2-12/13) retrieval + swarm ask pipeline.
- Byggt:
  - Snowflake retrieval med filters (topics/entities/source_type/date range) och row-fetch när connector finns.
  - Swarm pipeline: route (FAST) -> retrieve -> analyze (STRONG vid behov) -> synthesize (citations).
  - Ollama JSON-output valideras via Pydantic för route/analyze/synthesize.
  - CLI `ask` uppdaterad till full pipeline.
  - Tester för retrieval och swarm-moduler.
- Kör lokalt:
  - `python -m app.cli.main ask "<question>"`
- Kända problem:
  - Snowflake-connector install uppgraderade botocore och kan krocka med aiobotocore i din globalenv.

## 2026-01-29 (P3-14)
- Mål/fas: Phase D (P3-14) memory layer (session/working/long-term).
- Byggt:
  - Postgres memory_items-table för working/long-term items.
  - Snowflake MEMORY-table i bootstrap.
  - Memory write/recall-moduler + CLI-kommandon.
  - Snowflake MERGE SQL för MEMORY + recall via SQL.
  - Tester för memory write/recall och MEMORY MERGE SQL.
- Kör lokalt:
  - `python -m app.cli.main memory-write --type working --text "Kom ihåg detta"`
  - `python -m app.cli.main memory-recall --query "Kom ihåg" --type working --limit 5`
- Kända problem:
  - Long-term publish kräver Snowflake credentials och connector.

## 2026-01-29 (P3-15)
- Mål/fas: Phase D (P3-15) Obsidian workflow integration.
- Byggt:
  - Obsidian watcher (watchdog) som triggar på markdown-filer.
  - Frontmatter-parse och command-dispatch till queue.
  - Output skrivs till `_outputs/<note>.output.md`.
  - CLI `obsidian-watch`.
  - Tester för frontmatter-parse och enqueue.
- Kör lokalt:
  - `python -m app.cli.main obsidian-watch`
- Kända problem:
  - Watcher triggar på varje file-modify och kan ge duplicerade körningar.

## 2026-01-29 (P4-16/17)
- Mål/fas: Phase E (P4-16/17) initiative scoring + report.
- Byggt:
  - Intake-validate av initiativpayload (Pydantic).
  - LLM scoring (strict JSON) med rubric och citations.
  - C-level rapport (markdown).
  - Publish till Snowflake (INITIATIVES + INITIATIVE_REPORTS).
  - CLI `score-initiatives`.
  - Tester för pipeline, report och publish SQL.
- Kör lokalt:
  - `python -m app.cli.main score-initiatives --input ./initiatives.json`
- Kända problem:
  - Publish kräver Snowflake-credentials.

## 2026-01-29 (P5)
- Mål/fas: Phase F (P5) GraphRAG extraction (entities/relations/claims + ontology seed).
- Byggt:
  - Entity + claim extraction via LLM (strict JSON).
  - Relation extraction via LLM (strict JSON).
  - Ontology seed artifact.
  - Job chaining från enrich_chunks -> graph_extract_entities -> graph_extract_relations.
  - Tester för entities/relations/ontology.
- Kör lokalt:
  - `python -m app.cli.main worker --lane nemotron`
  - `python -m app.cli.main worker --lane oss20b`
- Kända problem:
  - Extraction kör på ett chunk-sample (max 20) i MVP.

## 2026-01-29 (P5 Graph publish + retrieve)
- Mål/fas: Phase F (P5) graph publish till Snowflake och graph retrieval (MVP).
- Byggt:
  - Publish av entities/relations/claims/ontology till Snowflake + receipt.
  - Graph retrieval modul (SQL mot ENTITIES/RELATIONS).
  - Job chaining: relations -> graph_publish, enrichment -> ontology seed.
  - Tester för publish och retrieve.
- Kör lokalt:
  - `python -m app.cli.main worker --lane nemotron`
  - `python -m app.cli.main worker --lane io`
- Kända problem:
  - Graph retrieval används inte av ask-pipeline ännu.

## 2026-01-29 (P5 Graph retrieval wiring)
- Mål/fas: Wire graph_retrieve in ask pipeline + k-hop (MVP).
- Byggt:
  - Graph retrieval med 1-hop traversal (entities + relations) i Snowflake.
  - Ask pipeline kombinerar text-retrieval + graph-retrieval.
  - Tester för graph_retrieve hop.
- Kör lokalt:
  - `python -m app.cli.main ask "<question>"`
- Kända problem:
  - Graph retrieval ger endast entities/relations (ingen text-snippet fusion).

## 2026-01-29 (P6 MCP server MVP)
- Mål/fas: Phase G (P6) MCP server (chat agent).
- Byggt:
  - MCP-style JSON-RPC server över stdio med tool list + call.
  - Tools för ingest, ask, memory write/recall, status.
  - CLI `mcp-server`.
  - Tester för MCP server tools.
- Kör lokalt:
  - `python -m app.cli.main mcp-server`
- Kända problem:
  - Voiceprint/MCP Apps UI är inte implementerat ännu.

## 2026-01-29 (P6 Voiceprint + diarization MVP)
- Mål/fas: Phase G (P6) voiceprint + diarization.
- Byggt:
  - Diarization stub som märker segment med speaker_local_id.
  - Voiceprint enroll/match/review artifacts.
  - Job chaining: transcribe -> diarize -> enroll -> match -> review.
  - Tester för voiceprint pipeline.
- Kör lokalt:
  - `python -m app.cli.main worker --lane transcribe`
  - `python -m app.cli.main worker --lane nemotron`
- Kända problem:
  - Diarization är heuristisk (single speaker) i MVP.

## 2026-01-29 (P6 Real diarization wiring)
- Mål/fas: Phase G (P6) real diarization via pyannote (optional).
- Byggt:
  - Diarization client (pyannote) + speaker assignment till transcript segments.
  - Fallback stub om PYANNOTE_TOKEN saknas.
  - Tester för speaker assignment.
- Kör lokalt:
  - Sätt `PYANNOTE_TOKEN` och (valfritt) `PYANNOTE_MODEL`.
- Kända problem:
  - Kräver pyannote.audio + HF-token.

## 2026-01-29 (P6 Audio denoise DeepFilterNet)
- Mål/fas: Phase G (P6) audio denoise med DeepFilterNet (optional).
- Byggt:
  - Denoise client wrapper + config.
  - Denoise modul som skriver `audio/denoised.wav` och kopplar in i transcribe.
  - Job chaining: ingest_youtube -> denoise_audio -> transcribe.
  - Tester för fallback när backend saknas.
- Kör lokalt:
  - Sätt `AUDIO_DENOISE_ENABLED=1` och `DEEPFILTERNET_CMD`.
- Kända problem:
  - Kräver DeepFilterNet CLI installerad.

## 2026-01-29 (P6 Voice Gallery MCP UI)
- Mål/fas: Phase G (P6) Voice Gallery UI (MCP).
- Byggt:
  - Voice gallery storage + EBUCore+ fields (given_name, family_name, title, role, affiliation, aliases, tags, notes).
  - MCP tools: voice_gallery_list, voice_gallery_update, voice_gallery_open.
  - MCP resources: ui://voice-gallery (minimal UI scaffold).
  - Tester för voice gallery och MCP tools.
- Kör lokalt:
  - `python -m app.cli.main mcp-server`
- Kända problem:
  - UI är minimal; edits sker via tool-anrop.
