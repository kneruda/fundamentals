# Phase 1 Code Review

Scope reviewed: schema/migration runner, section parsers, orchestrator, and Phase 1 tests.

Verification run during review:
- `uv run pytest tests/test_phase1.py` (30 passed)
- `uv run ruff check .` (clean)

## Findings (ordered by severity)

### 1) Medium: Migration tracking is fragile because script application is self-recorded

`_run_migrations` in `src/schema/runner.py` decides whether to run a file by checking `_schema_migrations`, but it does **not** insert a migration record itself. It relies on each SQL file to contain its own `INSERT INTO _schema_migrations ...`.

Impact:
- A future migration file that forgets this insert will be re-applied every run.
- Idempotency becomes convention-dependent instead of runner-enforced.

- Have the Python migration runner insert `script.stem` into `_schema_migrations` after successful execution (in the same transaction), and keep SQL files focused on schema/data changes only.

### 2) Low: Phase 1 tests are deep for AAPL, but seed-universe coverage is absent

The parser and schema tests are strong, but automated validation currently exercises one fixture ticker (`AAPL`) rather than a mini seed-universe set.

Impact:
- Field-shape or nullability differences that occur on other sectors/tickers may not be caught until later phases.

Recommendation:
- Add a small multi-ticker fixture test (2-3 names with different statement sparsity patterns) that runs `ingest_ticker` and verifies all target tables still load successfully.

## Open questions / assumptions

- Restatement semantics are now clarified and aligned in `PLAN.md` and `AGENTS.md` as in-place natural-key updates with latest value retained.

## Secondary summary

Phase 1 implementation quality is generally strong and test coverage is good for parser correctness and idempotency. The main remaining risk is migration bookkeeping being delegated to SQL file authors, with a smaller gap around single-ticker fixture breadth.
