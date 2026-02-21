# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and follows semantic intent.

## [Unreleased]

### Added

- Structured intake metadata for source context (`speaker`, `organization`, `event_date`, `source_metadata`) in `ingest_auto` and MCP intake UI/tool schema.
- EBUCore+-inspired manifest block (`metadata.ebucore_plus`) seeded from intake metadata.
- Central prompt template loader (`app/core/prompts.py`) with prompt files in `app/prompts/`.
- Configurable relation prompt chunk cap via `AURORA_GRAPH_RELATIONS_MAX_CHUNKS`.
- Transcript post-processing step (`transcript_markdown`) that writes `transcript/summary.json` and `transcript/summary.md` with cleaned transcript + summaries.

### Changed

- Prompt text moved out of Python modules into template files (`app/prompts/*.txt`) for graph, enrich, swarm, and initiative scoring flows.
- Worker bootstrap script now prefers a Python interpreter that has a transcription backend available (`whisper` CLI or `faster_whisper`).
- Transcription step now persists `transcript/source.srt` regardless of backend output stem (e.g. `denoised.srt`).
- Default Ollama model names normalized to `gpt-oss:20b` and `nemotron-3-nano:30b`.
- README/.env example updated with new metadata fields, worker restart commands, and graph relation chunk-cap setting.

## [0.1.0] - 2026-02-17

### Added

- Memory routing by `memory_kind` (`semantic`/`episodic`/`procedural`) across write/retrieve/recall.
- Explicit remember-hook in ask flows (CLI + MCP) with short-circuit for pure remember commands.
- Consolidation and supersede trails for contradictory memory values.
- Retrieval feedback reranking loop with decay and cluster-cap controls.
- Scope isolation and default scope fallback (`user_id`/`project_id`/`session_id`) across CLI + MCP memory flows.
- Optional PII egress policy (`off`/`pseudonymize`/`redact`) with run-log reason codes.
- Codex Desktop MCP bootstrap script and mobile CLI wrappers.
- Intake UI drag-and-drop support plus quick-action buttons (`Importera`, `Fraga`, `Kom ihag`, `TODO`) with in-UI explanations.

### Changed

- README expanded with Codex UI flow, mobile flow, and new policy/scope controls.
- Research index extended with AI Act + GDPR egress guidance.
