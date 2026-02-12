# Research: Ralph agent loop (snarktank/ralph)

Source: https://github.com/snarktank/ralph

## Overview
Ralph is an autonomous **agent loop** that repeatedly runs an AI coding tool
(Amp or Claude Code) until all PRD items pass. Each iteration is a *fresh
context* run; memory is persisted only via git history and a small set of
files.

## Core loop
1) Pick highest‑priority story in `prd.json` with `passes: false`
2) Run AI tool with a prompt template (Amp or Claude Code)
3) Execute quality gates (typecheck/tests)
4) If pass: commit changes + mark story `passes: true`
5) Append learnings to `progress.txt`
6) Repeat until all stories pass or max iterations reached

## Key files
- `ralph.sh` — the bash loop, supports `--tool amp|claude`
- `prompt.md` / `CLAUDE.md` — tool‑specific prompt templates
- `prd.json` — structured user stories + status
- `progress.txt` — append‑only learnings between iterations
- `skills/prd/` + `skills/ralph/` — skills to create PRD and convert to JSON

## Design principles
- **Fresh context per iteration** (no compounding drift)
- **Small tasks** only — each PRD item must fit in one context window
- **Feedback loops** (tests/typecheck) are required
- **Explicit stop condition**: `<promise>COMPLETE</promise>`
- **Auto‑handoff** for long tasks (Amp setting)

## Safety model
- Commits are created only after quality checks pass
- State is explicit and versioned (`prd.json`, git log)
- `progress.txt` captures “lessons learned” for the next iteration

## Workflow summary
1) Create PRD via skill → `tasks/prd-*.md`
2) Convert PRD to `prd.json` via skill
3) Run `./scripts/ralph/ralph.sh` with max iterations
4) Iterate until all stories pass or stop condition hits

## Why it matters for Aurora
If we want a similar loop in Aurora:
- Use `prd.json` (or equivalent) to track tasks and acceptance
- Enforce micro‑diff limits and test gates
- Persist learnings in a simple file
- Require explicit stop signal to end the loop

## References
- Geoffrey Huntley’s Ralph pattern: https://ghuntley.com/ralph/
- Amp CLI: https://ampcode.com/manual
- Claude Code: https://docs.anthropic.com/en/docs/claude-code
