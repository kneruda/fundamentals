# Phase 3 Code Review

Scope reviewed: `src/universe.py`, `scripts/add_ticker.py`, `scripts/seed_universe.py`, `scripts/load_daily.py`, and `tests/test_phase3.py`.

Verification run during review:
- `uv run pytest tests/test_phase3.py` (11 passed)
- `uv run pytest` (56 passed)

## Findings (ordered by severity)

### 1) Medium: `add_ticker(..., notes=...)` does not apply updated notes on re-add

`src/universe.py` inserts `notes` on first add, but the conflict path only sets `active = true`:

- `INSERT ... ON CONFLICT (ticker) DO UPDATE SET active = true`

Impact:
- Re-adding an existing ticker with new notes silently ignores the new `notes` argument.
- This makes the function signature misleading and prevents note updates through the Phase 3 CLI/API path.

Recommendation:
- Update the conflict clause to apply `notes = excluded.notes` (or explicitly preserve old notes when `notes is None`, if that is the intended behavior).

### 2) Medium: `add_ticker` writes universe row after ingest, allowing orphaned warehouse data on late failure

In `src/universe.py`, `add_ticker` calls `fetch_and_ingest(...)` first, then upserts `universe`.

Impact:
- If ingestion succeeds but the final universe upsert fails (or process exits between those operations), historical data can be loaded without a corresponding `universe` row.
- That creates a recoverability gap and can hide partially onboarded tickers from universe-driven workflows.

Recommendation:
- Use an explicit transaction boundary for the onboarding flow or record an "in progress" universe row before ingest and finalize it after success.

### 3) Low: Phase 3 tests do not assert `load_daily.py` universe-table sourcing behavior

Phase 3 requires `scripts/load_daily.py` to read active tickers from `universe` (not YAML). Implementation appears correct via `ingest_universe`, but this contract is not directly asserted in `tests/test_phase3.py`.

Impact:
- A future refactor could regress the source-of-truth behavior without a targeted failing test.

Recommendation:
- Add a focused test that seeds `universe` with active/inactive rows and verifies only active table rows are processed by the daily loader path.

## Open questions / assumptions

- This review treats `notes` as user-editable metadata that should update when explicitly passed to `add_ticker`; if notes are intentionally write-once, that should be documented in `PLAN.md`/`AGENTS.md`.

## Secondary summary

Phase 3 is in good shape overall: core add/remove/list/seed workflows and idempotency tests pass, and the canonical ticker preservation issue from Phase 2 appears addressed. The main follow-ups are onboarding robustness (`add_ticker` ordering/transactionality) and notes update semantics.
