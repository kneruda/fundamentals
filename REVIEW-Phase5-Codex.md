# Code Review: Phases 1-5

Scope reviewed: schema and migrations, section ingestion, vendor fetch/orchestration, universe management, computed views, Streamlit query/page layer, scripts, and tests through Phase 5.

Verification run during review:

- `uv run pytest` - 93 passed
- `uv run ruff check .` - clean
- `uv run black --check .` - failed; 7 files would be reformatted

## Findings

### 1. High: Invalid vendor responses can still activate a ticker

`src.universe.add_ticker()` depends on `fetch_and_ingest()` raising to reject invalid tickers, but `src.ingest.orchestrator.ingest_ticker()` catches and logs every section error without propagating failure. If EODHD returns a 200 response with an error payload, such as `{"Error": "Ticker Not Found."}`, `ingest_general()` fails on required `security_master` fields, the failure is swallowed, `analyst_snapshot` can still insert a mostly-null row, and `add_ticker()` marks the ticker active.

I confirmed this with a mocked EODHD error payload: `FAKE` ended up in `universe` with `active = true`, no `security_master` row, and one `daily_forward_snapshot` row.

Impact:

- The Universe UI/CLI can accept invalid tickers as active holdings.
- The dashboard can show active tickers with missing core data.
- The Phase 3 contract, "If EODHD rejects the ticker, this raises and the universe row is never written," is not actually enforced for 200-style vendor error payloads.

Recommendation:

- Validate fetched fundamentals before ingestion, at minimum requiring a `General` block with `Code`, `Exchange`, and `CurrencyCode`, and reject known vendor error shapes.
- Have `fetch_and_ingest()` verify that core sections loaded successfully, especially `security_master` and prices, before returning success to `add_ticker()`.
- Keep per-section logging for daily refreshes, but expose an explicit "strict" mode for add/backfill flows where missing core sections raises.

Relevant files:

- `src/universe.py`
- `src/ingest/orchestrator.py`
- `src/ingest/sections/general.py`
- `tests/test_phase3.py`

### 2. Medium: `adjusted_close` is updated only for dates present in the new feed

`src/ingest/sections/prices.py` upserts `adjusted_close` for incoming rows, but it does not do the planned ticker-scoped replacement of the entire `adjusted_close` column. The existing test changes every row in the same full fixture, so it proves updates work when the date set is identical. It does not cover stale warehouse rows that are absent from the latest vendor file.

Impact:

- If EODHD removes, corrects, truncates, or temporarily omits dates, old `adjusted_close` values can remain in `prices_daily`.
- The table can drift from the current vendor file, violating the project's special adjusted-close rule.

Recommendation:

- Stage the latest price payload in a temp table inside a transaction.
- Either delete ticker/date rows no longer present in the staged feed, or explicitly set stale `adjusted_close` values to `NULL` while preserving raw OHLC only if that is intentional.
- Add a test where the warehouse contains an extra historical date not present in the re-ingested price file.

Relevant files:

- `src/ingest/sections/prices.py`
- `tests/test_phase2.py`

### 3. Medium: "Next Earnings" uses fiscal period end, not an earnings event date

`queries.ticker_header()` computes `next_earnings` from `earnings_events` with `eps_actual IS NULL AND fiscal_period_end > CURRENT_DATE`, then displays `fiscal_period_end` as "Next Earnings." For a normal upcoming report, the fiscal period often ends before the report date. With current fixture timing, this logic returns no next earnings row even though forward estimate periods exist.

Impact:

- The Deep Dive header can show `-` when the next report is pending.
- When it does show a value, it is a fiscal period end, not an earnings date, so the label is misleading.

Recommendation:

- Rename this field to "Next Fiscal Period" if that is all the vendor data supports today.
- If the UI needs an actual earnings date, source it from a calendar endpoint or another vendor field that carries future report dates.
- Add a test with a completed fiscal period whose report date is still in the future.

Relevant files:

- `src/app/queries.py`
- `src/app/pages/1_Deep_Dive.py`

### 4. Medium: Earnings reaction ignores before/after-market timing

`queries.earnings_history()` joins prices on `prices_daily.date = earnings_events.report_date` and computes `(next_close / report_date_close - 1)`. That is reasonable only for after-market reports on trading days. For before-market reports, the immediate reaction is usually prior close to report-date close. For weekend/holiday report dates, the exact-date join produces `NULL`.

Impact:

- The "Next-Day Price Reaction" panel can understate, overstate, or miss the actual event reaction.
- This is a user-facing analytical panel, so wrong event-window logic is more damaging than a missing value.

Recommendation:

- Use `before_after_market` to choose the event window:
  - before-market: previous trading close to report-date close
  - after-market: report-date close to next trading close
  - unknown/non-trading report date: first appropriate trading dates around the report date
- Add synthetic tests for before-market, after-market, and weekend report dates.

Relevant files:

- `src/app/queries.py`
- `src/app/pages/1_Deep_Dive.py`

### 5. Medium: CLI scripts can drift from configured warehouse paths

The app query layer reads `config/settings.yml` and resolves the warehouse path relative to the project root. The CLI scripts use `WAREHOUSE_PATH` or the literal default `data/warehouse.duckdb`, relative to the current working directory. If the scripts are run outside the repo root or `config/settings.yml` changes, ETL and UI can silently point at different DuckDB files.

Impact:

- `seed_universe.py`, `add_ticker.py`, or `load_daily.py` may populate a warehouse the Streamlit app never reads.
- This is especially easy to hit when scheduling `load_daily.py` from cron in Phase 6.

Recommendation:

- Centralize warehouse path resolution in one helper, probably the same settings-based helper used by `src/app/queries.py`.
- Let `WAREHOUSE_PATH` override the config only deliberately and document that behavior.
- Add a script-level test that patches the config path and verifies scripts open the same warehouse as the app layer.

Relevant files:

- `src/app/queries.py`
- `scripts/load_daily.py`
- `scripts/add_ticker.py`
- `scripts/seed_universe.py`

### 6. Low: Formatting check is currently failing

`uv run black --check .` reports that these files would be reformatted:

- `src/compute/__init__.py`
- `src/schema/runner.py`
- `src/app/pages/2_Universe.py`
- `src/app/Home.py`
- `src/app/queries.py`
- `tests/test_phase4.py`
- `src/app/pages/1_Deep_Dive.py`

Impact:

- The repo does not meet the documented Phase 0/AGENTS build command surface.
- CI will fail if it enforces the documented black check.

Recommendation:

- Run `uv run black .` and commit only formatting changes, or update the documented formatting tool if the project is intentionally using Ruff formatter instead.

### 7. Low: Streamlit width API is already producing deprecation warnings

The running Streamlit app logs repeated warnings that `use_container_width` should be replaced with `width`, and that `use_container_width` will be removed after 2025-12-31.

Impact:

- The UI still runs today, but this is a near-term compatibility issue for an app dated in 2026.

Recommendation:

- Replace `use_container_width=True` with `width="stretch"` and `use_container_width=False` with `width="content"` across Streamlit calls.

Relevant files:

- `src/app/Home.py`
- `src/app/pages/1_Deep_Dive.py`
- `src/app/pages/2_Universe.py`

## Test Coverage Gaps

- Add a test for EODHD 200-style error JSON and empty price payloads flowing through `add_ticker()`; this should raise and leave no active universe row.
- Add adjusted-close replacement coverage where the existing warehouse has dates absent from the latest source file.
- Add earnings-reaction tests that cover before-market, after-market, and non-trading report dates.
- Add a UI/query test for "next earnings" semantics, or rename the field if only fiscal period end is available.
- Add at least one recorded HTTP-contract test for each EODHD endpoint. The current mocked tests are useful for request construction and retries, but they do not catch vendor response-shape drift.
- Consider adding a small multi-ticker fixture set. The AAPL fixture is deep, but it does not exercise field sparsity across banks, loss-making software names, non-dividend payers, non-US tickers, or delisted names.
- Page files are not imported or smoke-tested directly. `tests/test_phase5.py` exercises the query layer, but not Streamlit page execution, formatting, or API compatibility warnings.

## Positive Notes

- The code is well organized around the intended boundaries: section ingestion modules, computed views, a single app query layer, and thin Streamlit pages.
- Point-in-time TTM joins now consistently use `earnings_events.report_date`, and the Phase 4 tests cover the most important no-lookahead P/E case.
- Canonical ticker preservation for suffixed tickers is now covered by tests.
- The migration runner now records applied migrations itself, which resolves the fragility noted in the Phase 1 review.
