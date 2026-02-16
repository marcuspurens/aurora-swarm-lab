# Research: Agent Memory Systems (Google + Anthropic + RMM)

Date: 2026-02-16
Scope: Indexera och jämföra centrala källor för agent-minne och mappa dem mot Aurora.

## Sources
- Google Memory Bank (generate memories):
  - https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/generate-memories
- Google agent memory architecture components:
  - https://docs.cloud.google.com/architecture/choose-agentic-ai-architecture-components
- Google ADK memory blog:
  - https://cloud.google.com/blog/topics/developers-practitioners/remember-this-agent-state-and-memory-with-adk/
- Google/Kaggle whitepaper (Context Engineering: Sessions & Memory):
  - https://www.kaggle.com/whitepaper-context-engineering-sessions-and-memory
- Anthropic Claude Code memory:
  - https://docs.anthropic.com/en/docs/claude-code/memory
- RMM paper (ACL 2025):
  - https://aclanthology.org/2025.acl-long.413/
- Google Generative Agents:
  - https://research.google/pubs/generative-agents-interactive-simulacra-of-human-behavior/

## Source index

### 1) Google Memory Bank
Fokus:
- Extrahera minnen från interaktioner.
- Konsolidera/skriv om minnen över tid.
- Klassificera topics/scope för bättre retrieval.

Relevans för Aurora:
- Matchar `memory_kind` + compaction/consolidation-spåret.
- Bra stöd för tydligare scope-modell (user/project/session).

### 2) Google Agent Memory Architecture
Fokus:
- Delar upp minne i lager (kort-/långtidsliknande roller).
- Visar hur state och memory samspelar i agentarkitektur.

Relevans för Aurora:
- Stöder nuvarande separation mellan session/working/long-term.
- Pekar på behov av tydligare policies för skrivning och återhämtning.

### 3) Google ADK Memory Blog
Fokus:
- Praktisk implementation av agent state + memory i produktionsliknande flöden.
- Mönster för när minnen ska skrivas och användas.

Relevans för Aurora:
- Bekräftar att explicit "remember" + policydriven write path är rätt.
- Stödjer förbättringar kring traceability och memory-governance.

### 4) Anthropic Claude Code Memory
Fokus:
- Hierarkisk, filbaserad minnesmodell.
- Deterministisk laddning/prioritet av instruktioner/minne.

Relevans för Aurora:
- Komplement till runtime-memory: passar bra för stabila regler/policies.
- Kan kombineras med `docs/decisions` och statiska agentregler.

### 5) RMM (Reflective Memory Management)
Fokus:
- Prospective + retrospective reflection.
- Justera retrieval baserat på vad som faktiskt hjälpte i efterhand.

Relevans för Aurora:
- Direkt grund för nu införd feedback-loop:
  - evidence/citation utfallet skrivs som feedback-minnen.
  - kommande retrieval får lätt reranking via cited/missed-signaler.

### 6) Generative Agents (Store/Reflect/Retrieve)
Fokus:
- Store -> Reflect -> Retrieve som kärncykel.
- Reflektion används för att få mer användbara, högre nivåns minnen.

Relevans för Aurora:
- Matchar pipeline-tänk för minneskvalitet.
- Ger stöd för framtida "reflection jobs" utanför ask-pathen.

### 7) Google/Kaggle: Context Engineering (Sessions & Memory)
Fokus:
- Tydlig uppdelning mellan session (kortsiktig, turn-baserad state) och memory (långsiktig, konsoliderad kunskap).
- Scope-modell för minnen (user/session/application) med stark isolering per användare.
- Konsolideringsoperationer som CREATE/UPDATE/DELETE/INVALIDATE.
- Memory relevance decay/forgetting (TTL/pruning) och asynkron memory-generation efter svar.

Relevans för Aurora:
- Stärker nuvarande riktning med scope-isolering + consolidation/supersede + feedback-loop.
- Matchar behov av fortsatt memory hygiene (decay + periodic cleanup jobs).
- Pekar på nästa säkerhetsnivå: tydligare provenance/guardrails mot memory poisoning.

## Comparison (kort)

Google-linjen:
- Tyngdpunkt på extraction + consolidation + scope i systemdesign.
- Whitepaper-linjen (Sessions & Memory): operationaliserar samma tema med livscykel-perspektiv
  (fetch -> prepare -> invoke -> upload) och tydlig separation mellan hot path (session) och background path (memory).

Anthropic-linjen:
- Tyngdpunkt på deterministisk, hierarkisk kontext/memory-laddning.

RMM-linjen:
- Tyngdpunkt på feedback-loop där retrievalutfall förbättrar nästa retrieval.

## Aurora mapping (2026-02-16)

Redan implementerat:
- Explicit remember-routing.
- `memory_kind`-klassning.
- Pre-compaction och konflikt-supersede.
- Retrospective retrieval feedback loop (RMM-liknande).
- Scope-isolering (user/project/session) i write/recall/retrieve.
- Feedback decay + cap per query-cluster.
- Revision trail för consolidation/supersede.
- `memory-stats` för observability i CLI + MCP.

Högst prioriterade fortsättningar:
1. Offline reflection/consolidation-jobb för periodisk minneshygien (whitepaper: background memory lifecycle).
2. Policy för forgetting/pruning på minnesnivå (inte bara feedback-signaler), inkl. TTL-strategier per memory_kind.
3. Hardening: provenance + safeguards mot memory poisoning och känslig data-överföring mellan scopes.

## Notes
- Denna sida är avsedd som index-notering. När en källa leder till ett konkret beslut, skapa ADR i `docs/decisions/`.
