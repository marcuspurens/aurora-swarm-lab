HANDOFF - 2026-02-20

Repo:
- /Users/mpmac/aurora-swarm-lab
- Branch: main
- Worktree: dirty (many in-progress changes from earlier sessions)

Goal:
- Full cleanup across machine + repo, and leave a stable single-path intake setup.

Done:
- Consolidated Aurora drop path to one canonical folder:
  - `/Users/mpmac/Documents/AuroraObsidian/Aurora Drop`
- Synced previous duplicate content from `/Applications/Aurora Drop` to canonical folder.
- Replaced `/Applications/Aurora Drop` with symlink to canonical folder:
  - `/Applications/Aurora Drop -> /Users/mpmac/Documents/AuroraObsidian/Aurora Drop`
- Removed duplicate local vault folder from repo root by moving it out:
  - `Aurora Obsedian/` moved to `/Users/mpmac/Documents/AuroraObsedian_repo_backup_20260220-084124`
- Added ignore rules to prevent accidental re-add:
  - `.gitignore`: `Aurora Obsedian/`, `Aurora Obsidian/`
- Queue hygiene:
  - Requeued stale `running` jobs (set back to `queued`) and kickstarted workers.
- Indexing for ORF PDF confirmed:
  - `ingest_doc=done`, `chunk_text=done`, `embed_chunks=done`
  - Embeddings exist in DB (`COUNT(*)=2` for this `source_id`).
- Stabilized embedding model in local env:
  - `.env`: `OLLAMA_MODEL_EMBED=snowflake-arctic-embed:latest` (works; `bge-m3` endpoint was hanging).

Not done:
- End-to-end enrichment/graph chain for that PDF is not fully green yet.
  - Current source-specific state still shows intermittent `running` on:
    - `enrich_doc`
    - `graph_extract_entities`
  - Both have previously timed out against Ollama.

Key decisions:
- Keep one real drop location under Documents and use symlink in `/Applications` for backward compatibility.
- Prefer non-destructive cleanup (move/symlink) over hard delete where possible.
- Use working embedding model (`snowflake-arctic-embed:latest`) to avoid stalled indexing.

Changed files (this cleanup session):
- `.gitignore`
- `.env` (local only)
- `docs/HANDOFF-2026-02-20-cleanup.md`

Environment/canonical paths:
- `OBSIDIAN_VAULT_PATH=/Users/mpmac/Documents/AuroraObsidian`
- `AURORA_DROPBOX_PATHS="/Users/mpmac/Documents/AuroraObsidian/Aurora Drop"`
- `/Applications/Aurora Drop` is now only a symlink to the canonical path above.

Verification:
- `ls -ld /Applications/Aurora Drop` -> symlink to canonical folder.
- `python -m app.cli.main status` -> queue active (done/failed/running counts visible).
- Source job check for ORF PDF:
  - `embed_chunks=done`
  - `enrich_chunks=done`
  - `enrich_doc` + `graph_extract_entities` still intermittently running/timeouts.

Next steps (priority):
1. Finish PDF pipeline deterministically:
   - Requeue only this source's stale `running` jobs.
   - Run `oss20b` lane manually with `.venv` and longer Ollama timeout until `enrich_doc`, `graph_extract_entities`, `graph_extract_relations`, `graph_publish` are done.
2. Add watchdog for stale `running` jobs:
   - Small maintenance step to auto-requeue `running` jobs older than threshold.
3. Optional hard cleanup:
   - If user wants, remove old backup folder:
     - `/Users/mpmac/Documents/AuroraObsedian_repo_backup_20260220-084124`

Risks/blockers:
- Ollama instability/timeouts on long jobs can leave jobs stuck in `running`.
- Different Python environments can cause inconsistent dependency availability if workers are not launched via `.venv`.
