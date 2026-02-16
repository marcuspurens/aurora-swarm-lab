# Handoff Playbook

This playbook keeps momentum when switching chat threads or model context.
It is optional, but recommended for long-running work.

## When To Start A New Thread

- Responses become generic or miss recent details.
- You switch subsystem (for example memory -> voiceprint).
- After a large refactor/merge.
- After long debugging where context is noisy.

## Minimum Handoff Content

- Goal: what should be finished next.
- Status: done vs not done.
- Decisions: key technical decisions and why.
- Changed files: exact paths.
- Verification: commands run and outcomes.
- Next steps: 1-3 concrete items in priority order.
- Risks/blockers: known failure points.

## Paste Template

```md
HANDOFF - <YYYY-MM-DD>

Repo:
- <absolute or workspace path>

Goal:
- ...

Done:
- ...

Not done:
- ...

Key decisions:
- ...

Changed files:
- path/a.py
- path/b.py

Verification:
- `pytest -q ...` -> ...
- `python -m ...` -> ...

Next steps (priority):
1. ...
2. ...
3. ...

Risks/blockers:
- ...
```

## Quick Pre-Handoff Commands

- `python -m app.cli.main context-handoff`
- `pytest -q` (or relevant subset)

## New Thread Starter Prompt

Use this as first message in the new thread:

```text
Continue from the handoff below.
Start with step 1 and run until verified done.
```

