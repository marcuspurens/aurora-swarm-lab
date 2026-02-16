# Architecture

## Dataflow: URL ingest (P1-5)
1) CLI `enqueue-url <url>` beräknar `source_version` genom att:
   - hämta HTML
   - extrahera readable text
   - normalisera whitespace
   - sha256 över canonical text
2) Jobbet `ingest_url` körs i `io`-lane.
3) Modulen `app/modules/intake/intake_url.py`:
   - sparar artifacts:
     - `raw/url.html`
     - `text/canonical.txt`
   - uppdaterar manifest med artifacts + stats
   - enqueuar `chunk_text`

## Dataflow: Document ingest (P1-6)
1) CLI `enqueue-doc <path>` skapar `source_id` som `file:<abs_path>` och `source_version` som sha256 över filbytes.
2) Jobbet `ingest_doc` körs i `io`-lane.
3) Modulen `app/modules/intake/intake_doc.py`:
   - extraherar text (TXT/DOCX/PDF)
   - sparar artifacts:
     - `raw/source.<ext>`
     - `text/canonical.txt`
   - uppdaterar manifest med artifacts + stats
   - enqueuar `chunk_text`

## Dataflow: YouTube/audio + Whisper (P1-7/8)
1) CLI `enqueue-youtube <url>`:
   - hämtar video-id
   - beräknar `source_version` via sha256 över nedladdad audio (m4a)
2) Jobbet `ingest_youtube` körs i `io`-lane:
   - laddar ner audio `audio/source.m4a`
   - enqueuar `denoise_audio` (om aktiverad)
   - uppdaterar manifest
3) Jobbet `denoise_audio` (transcribe-lane):
   - skriver `audio/denoised.wav`
   - enqueuar `transcribe_whisper`
4) Jobbet `transcribe_whisper`:
   - kör Whisper CLI
   - sparar `transcript/source.srt` och `transcript/segments.jsonl`
   - uppdaterar manifest med segment-count
   - enqueuar `chunk_transcript`
   - enqueuar `diarize_audio`

## Dataflow: Chunking + Enrichment + Publish (P1-9/10/11)
1) `chunk_text` (oss20b-lane):
   - läser `text/canonical.txt`
   - skriver `chunks/chunks.jsonl`
   - enqueuar `enrich_doc` + `enrich_chunks`
2) `chunk_transcript` (oss20b-lane):
   - läser `transcript/segments.jsonl`
   - skriver `chunks/chunks.jsonl`
   - enqueuar `enrich_chunks`
3) `enrich_doc` (oss20b-lane):
   - LLM sammanfattar dokument
   - skriver `enrich/doc_summary.json`
4) `enrich_chunks` (oss20b-lane):
   - LLM taggar topics/entities per chunk
   - skriver `enrich/chunks.jsonl`
   - enqueuar `publish_snowflake`
   - enqueuar `graph_ontology_seed`
   - enqueuar `graph_extract_entities`
5) `publish_snowflake` (io-lane):
   - bygger MERGE SQL för DOCUMENTS + KB_SEGMENTS
   - försöker köra mot Snowflake
   - skriver `publish/snowflake_receipt.json`

## Dataflow: Retrieval + Ask (P2-12/13)
1) `retrieve_snowflake`:
   - bygger SQL mot `KB_SEGMENTS` + `DOCUMENTS`
   - filter: topics/entities/source_type/date range
2) `graph_retrieve`:
   - 1-hop traversal från entities (ENTITIES/RELATIONS)
3) `swarm` ask pipeline:
   - route (fast model) -> intent + filters + top_k
   - retrieve (Snowflake) + graph_retrieve
   - analyze (strong model) vid behov
   - synthesize (fast/strong) med citations

## Dataflow: Memory (P3-14)
1) `memory-write`:
   - lagrar item i Postgres `memory_items`
   - kan publicera till Snowflake `MEMORY`
2) `memory-recall`:
   - söker i Postgres (LIKE/ILIKE)
   - valfritt även Snowflake (TEXT ILIKE)

## Dataflow: Obsidian workflow (P3-15)
1) Watcher lyssnar på `.md`-ändringar i `OBSIDIAN_VAULT_PATH`.
2) Frontmatter `aurora_command` triggar job enqueue.
3) Output skrivs till `_outputs/<note>.output.md`.

## Dataflow: Initiative scoring + report (P4-16/17)
1) CLI `score-initiatives --input <json>`:
   - validerar payload
   - LLM scoring (strict JSON)
   - bygger C-level report
   - publicerar till Snowflake (INITIATIVES + INITIATIVE_REPORTS)

## Dataflow: GraphRAG extraction + publish (P5)
1) `graph_extract_entities` (nemotron-lane):
   - läser enriched chunks
   - skriver `graph/entities.jsonl` + `graph/claims.jsonl`
   - enqueuar `graph_extract_relations`
2) `graph_extract_relations` (nemotron-lane):
   - läser chunks + entities
   - skriver `graph/relations.jsonl`
   - enqueuar `graph_publish`
3) `graph_ontology_seed`:
   - skriver `graph/ontology.json`
4) `graph_publish` (io-lane):
   - publicerar ENTITIES/RELATIONS/CLAIMS/ONTOLOGY
   - skriver `graph/publish_receipt.json`

## Dataflow: Voiceprint + diarization (P6)
1) `diarize_audio` (transcribe-lane):
   - läser `transcript/segments.jsonl`
   - kör pyannote diarization om `PYANNOTE_TOKEN` är satt
   - skriver `transcript/segments_diarized.jsonl`
2) `voiceprint_enroll` (nemotron-lane):
   - läser diarized segments
   - skriver `voiceprint/voiceprints.jsonl`
3) `voiceprint_match` (nemotron-lane):
   - skriver `voiceprint/matches.jsonl`
4) `voiceprint_review` (nemotron-lane):
   - skriver `voiceprint/review.json`

## Dataflow: MCP server (P6)
1) `mcp-server` körs över stdio och exponerar tools för ingest, ask och memory.
2) Voice Gallery UI exponeras som `ui://voice-gallery`.

## Kontrakt
- URL `source_version` = sha256 över normaliserad canonical text.
- File `source_version` = sha256 över råa filbytes.
- YouTube `source_version` = sha256 över audio-bytes (m4a).
- Denoise producerar `audio/denoised.wav`.
- Chunking producerar `chunks/chunks.jsonl`.
- Enrichment producerar `enrich/doc_summary.json` och `enrich/chunks.jsonl`.
- Publish skriver `publish/snowflake_receipt.json`.
- Memory lagras i Postgres `memory_items` och Snowflake `MEMORY`.
- Graph artifacts: `graph/entities.jsonl`, `graph/relations.jsonl`, `graph/claims.jsonl`, `graph/ontology.json`, `graph/publish_receipt.json`.
- Voiceprint artifacts: `transcript/segments_diarized.jsonl`, `voiceprint/voiceprints.jsonl`, `voiceprint/matches.jsonl`, `voiceprint/review.json`.
- Voice Gallery data stored in `voice_gallery.json`.
