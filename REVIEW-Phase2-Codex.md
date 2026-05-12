# Phase 2 Code Review

Scope reviewed: vendor client, price ingestion, fetch/orchestration flow, daily loader script, and Phase 2 tests.

Verification run during review:
- `uv run pytest tests/test_phase2.py` (14 passed)
- `uv run pytest` (45 passed)

## Findings (ordered by severity)

### 1) High: Ticker normalization can corrupt identifiers for suffixed symbols

`src/ingest/orchestrator.py` derives the warehouse key as `data["General"]["Code"]` when present. For EODHD, `General.Code` is typically the bare symbol (for example `AAPL`), not the full vendor-format ticker (for example `AAPL.US` or `7203.TSE`).

Impact:
- If ingestion is called with suffixed tickers, rows can be written under a different ticker key than the universe key.
- This can break joins, deduplication, and non-US support assumptions from project conventions.

Recommendation:
- Preserve the canonical runtime ticker argument when ingesting fetched data, and only fall back to `General.Code` for local/legacy fixture ingestion where no canonical ticker is provided.

### 2) Medium: `adjusted_close` replacement is implemented as UPSERT, not strict full-column replacement

`src/ingest/sections/prices.py` upserts all price fields including `adjusted_close` for dates present in the new payload. This updates known rows correctly, but it does not clear or reconcile stale dates that may already exist in `prices_daily` but are absent from the current feed.

Impact:
- If the source date set ever changes (vendor correction, truncation, bad cached file), `prices_daily.adjusted_close` may no longer exactly match "the source file values for every date currently in warehouse".

Recommendation:
- Implement the Phase 2 intended pattern explicitly: stage the current feed in a temp table and run a ticker-scoped replacement flow that guarantees `adjusted_close` parity with the staged source set.

### 3) Low: Vendor-client tests use mocked calls, not recorded HTTP fixtures

`tests/test_phase2.py` validates request construction and retry behavior via monkeypatching/mocks. This is useful but does not satisfy the "recorded HTTP responses (vcr.py or similar)" acceptance target in `PLAN.md`.

Impact:
- Contract drift against real API responses (shape changes, edge statuses, headers) is less likely to be caught early.

Recommendation:
- Add at least one VCR-backed test per endpoint (`fetch_fundamentals`, `fetch_prices`) and keep unit mocks for retry/error-path precision.

## Open questions / assumptions

- This review assumes the canonical ticker convention in `AGENTS.md` remains authoritative (`ticker` should support vendor-format symbols like `AAPL.US` and `7203.TSE`).
- If runtime tickers are intentionally constrained to bare US symbols only, finding #1 becomes a future-proofing risk rather than an active bug.

## Secondary summary

Phase 2 is largely solid and test-backed; ingestion, fetch orchestration, and daily loading are all implemented and passing tests. The highest-priority follow-up is ticker key consistency for suffixed symbols, with secondary hardening around strict adjusted-close replacement semantics and API-contract test realism.
