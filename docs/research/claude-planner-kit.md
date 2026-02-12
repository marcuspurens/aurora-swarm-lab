# Research: Claude Planner Kit (agent loop)

Source: https://github.com/johanbaath/claude-planner-kit/

## Overview
Claude Planner Kit is a two‑phase agent loop for Claude Code:
1) **Planner** (`/create-plan`) reads repo signals and produces a deterministic plan.
2) **Implementor** (`/implement-plan`) executes the plan in small, bounded diffs.

It is designed to reduce agent drift and make changes auditable.

## Key mechanics
- **Deterministic plan schema**: `implementor.v1` with stable IDs, leaf checkboxes,
  constraints, approvals, acceptance criteria.
- **Guarded execution**: ≤150 line diffs per step, optional lint/test/tsc gates.
- **Explicit stop rules**: `--stop-when-questions` halts if blockers arise.
- **Auditable state**: logs and state are written to `.planner/implement/`.

## Commands and options
- `/create-plan "goal"`
  - Writes `.planner/plan.md` (backups if exists).
- `/implement-plan`
  - Executes plan in micro‑steps.
  - Options: `--dry-run`, `--task T-X`, `--max-lines N`, `--max-steps K`,
    `--stop-when-questions`.

## Security posture
- External lookups via Context7 **avoid sending code**; only library identifiers.
- No dependency installs unless plan includes `APPROVED:` entries.
- No git commits are made automatically.
- `.planner/` should be treated as state/logs and git‑ignored.

## Why this matters for an agent loop
The pattern introduces clear **phase separation**:
- **Think**: produce a bounded plan with explicit acceptance criteria.
- **Act**: execute in small, reviewable steps.
This is a repeatable, safe loop for larger tasks.

## Relevance to Aurora
If we adopt a similar loop, we can:
- Produce **auditable** plans for larger changes.
- Enforce **small, reviewable diffs** in automation.
- Add a **pause mechanism** when a decision is needed.

Not strictly needed for day‑to‑day ingest/chat flows, but valuable for
multi‑step dev tasks.

## Suggested adaptations (if we build similar)
- Keep plan schema minimal and explicit.
- Enforce `max-lines` for each micro‑diff.
- Log artifacts to a dedicated directory (e.g., `.planner/`).
- Integrate a "stop on question" rule to prevent runaway edits.
