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
