# Phase 4 Code Review

Scope reviewed: `src/compute/ttm.py`, `src/compute/multiples.py`, `src/compute/technicals.py`, view setup in `src/schema/runner.py`, and `tests/test_phase4.py`.

Verification run during review:
- `uv run pytest tests/test_phase4.py` (19 passed)
- `uv run pytest` (75 passed)

## Findings (ordered by severity)

### 1) High: TTM revenue/EBITDA/FCF use statement `report_date`, not earnings-event `report_date`

`PLAN.md` Phase 4 requires TTM timing to use the becomes-known timestamp from `earnings_events.report_date`. Current implementation:

- `ttm_eps` uses `earnings_events.report_date` (correct).
- `ttm_revenue` and `ttm_ebitda` in `src/compute/ttm.py` use `income_statement.report_date`.
- `ttm_fcf` in `src/compute/ttm.py` uses `cash_flow.report_date`.

This is not equivalent in current fixture data. Spot-check on AAPL shows many mismatches between statement and earnings report dates (e.g. `2026-03-31` has `income_statement.report_date=2026-05-01` vs `earnings_events.report_date=2026-04-30`; mismatch count: 128 joined quarters for both income and cash-flow comparisons).

Impact:
- Point-in-time alignment differs across multiples: P/E switches on earnings date, while P/S, EV/EBITDA, and FCF yield may switch later.
- This introduces avoidable look-ahead/lag inconsistency in cross-multiple comparisons around earnings release windows.

Recommendation:
- Anchor all TTM views to `earnings_events.report_date` (joining statements by `(ticker, fiscal_period_end)`), then keep ASOF joins in `trailing_multiples_daily` on that unified report date.

### 2) Medium: Beta benchmark ticker is hardcoded to `SPY`, ignoring configured benchmark

`src/compute/technicals.py` uses:
- `WHERE ticker = 'SPY'` for benchmark returns
- `WHERE lr.ticker <> 'SPY'` to exclude benchmark row

But `config/settings.yml` defines benchmark as `SPY.US`.

Impact:
- `beta_spy_252d` remains NULL when benchmark data is loaded under configured ticker (`SPY.US`), which is the default convention in this repo.
- Changing benchmark in config has no effect on technicals output.

Recommendation:
- Parameterize benchmark ticker from settings and use it when creating `technicals_daily` (and exclude that same configured ticker from output rows).

### 3) Low: Phase 4 tests miss two “Done when” acceptance checks from plan

`tests/test_phase4.py` is strong on formulas and point-in-time mechanics, but does not currently assert:
- AAPL trailing P/E vs public-source sanity (~1% tolerance).
- Negative-EPS behavior on actual MVP tickers (`RBLX`, `U`) specifically (current test uses synthetic `LOSS` ticker).

Impact:
- Regressions against stated Phase 4 completion criteria may pass CI despite diverging from plan-level validation goals.

Recommendation:
- Add one regression test (or documented acceptance script) for AAPL 5y P/E sanity and one fixture-backed check for `RBLX`/`U` NULL P/E behavior once those fixtures are available.

## Open questions / assumptions

- This review assumes the wording in `PLAN.md` is authoritative for `report_date` source (`earnings_events` for all TTM views).
- If the team intentionally prefers statement `filing_date` for revenue/EBITDA/FCF timing, that design choice should be documented in `PLAN.md` and `AGENTS.md` to avoid ambiguity.

## Secondary summary

Phase 4 implementation quality is solid overall, with broad passing tests and clean view orchestration. The highest-priority fix is unifying TTM timing keys to preserve point-in-time consistency across all trailing multiples; next is wiring beta benchmark ticker to configuration.
