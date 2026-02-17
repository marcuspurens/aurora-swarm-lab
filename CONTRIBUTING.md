# Contributing to Aurora Swarm Lab

Thanks for contributing.

## Workflow

1. Create a branch from `main`.
2. Make focused changes with clear commit messages.
3. Run tests before opening a PR:

```bash
pytest -q
```

4. Update docs when behavior changes (`README.md`, `docs/decisions/`, `docs/research/`).
5. Open a pull request with:
- Problem statement
- What changed
- How you tested
- Risks/rollout notes

## Development Setup

1. Copy env file:

```bash
cp .env.example .env
```

2. Initialize queue DB:

```bash
python -m app.cli.main bootstrap-postgres
```

3. Start relevant workers depending on feature area.

## Test Expectations

- New logic should include tests in `tests/`.
- Keep tests deterministic and offline where possible.
- For behavior that touches memory/retrieval flows, add at least one regression test.

## Code Style

- Keep modules small and focused.
- Prefer explicit naming and defensive fallbacks in runtime paths.
- Avoid destructive migrations or data rewrites without an ADR.

## Commits

- Use descriptive messages in imperative form.
- Keep unrelated changes out of the same commit.

