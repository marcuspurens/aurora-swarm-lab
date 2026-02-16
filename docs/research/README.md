# Research Notes

Den här mappen innehåller research i Markdown (`.md`) för Aurora Swarm Lab.

## Syfte
- Samla externa källor och slutsatser på ett ställe.
- Skilja på research (`docs/research`) och beslut (`docs/decisions`).
- Göra det enkelt att gå från "läst" -> "implementerat".

## Rekommenderad filnamnspraxis
- `YYYY-MM-DD-<topic>.md`
- Exempel: `2026-02-16-agent-memory-systems-index.md`

## Mall (kopiera)
```md
# Research: <titel>

Date: YYYY-MM-DD
Scope: <vad noten täcker>

## Sources
- <url>

## Key takeaways
- ...

## Relevance to Aurora
- ...

## Suggested next steps
1. ...
```

## Index
| Note | Fokus |
|---|---|
| `docs/research/2026-02-16-agent-memory-systems-index.md` | Google Memory Bank, Google agent memory architecture, ADK memory, Claude Code memory, RMM, Generative Agents |
| `docs/research/anthropic-ralph-loop.md` | Ralph-loop inspiration och loop design |
| `docs/research/claude-planner-kit.md` | Planner/Implementor-loop och guardrails |
| `docs/research/ralph-agent-loop.md` | Agent loop med PRD + quality gates |
