# AGENTS.md

> Guidance for AI coding agents (and humans) working on this project.
> If a `CLAUDE.md` is desired, make it a symlink or short pointer to this file
> so the two never drift.

## Mission

Build a personal equity fundamentals dashboard that tracks valuation,
profitability, growth, balance-sheet strength, and analyst expectations for a
user-managed universe of stocks. The dashboard supports three modes:

1. **Universe management** — add or remove tickers through a simple UI; new
   tickers backfill all available historical data immediately.
2. **Drill-down** on a single ticker, with full statements, historical
   multiples, and analyst expectations in one view.
3. **Screens** that filter the whole universe on configurable criteria —
   trailing fundamentals, relative-to-history valuation, and (once enough
   snapshot history accumulates) forward-looking analyst signals.

## Scope

### In scope
- A managed universe of equities (table-backed, user-editable through UI/CLI)
- Static company data (identifiers, sector classification, fiscal year end,
  currency, country)
- Quarterly fundamentals (TTM/MRQ aggregates from the vendor `Highlights`
  block)
- Full quarterly financial statements (income statement, balance sheet, cash
  flow) from the `Financials` block in the same vendor file
- Earnings events (estimates, actuals, surprises, report dates)
- Dividend events and annual history
- Analyst expectations (consensus rating, target price, forward EPS estimates
  per future fiscal period)
- Daily price history from the vendor (separate endpoint, same vendor)
- FX rates (USD is the reporting currency; design supports non-USD tickers)

### Out of scope — DO NOT IMPLEMENT
The following fields exist in the source JSON but we have **explicitly
decided not to track them**. If a future requirement asks for any of these,
raise it for discussion before implementing — the omissions are deliberate,
not oversights.

- `Holders.*` (institutional and fund holdings)
- `InsiderTransactions.*` (Form 4 transactions)
- `General.Officers` (named executives)
- `Technicals.*` (we derive technicals from price history ourselves)
- `SharesStats.SharesShort*` and short-interest fields
- `ESGScores.*` (vendor self-disclaims it is not production-ready)
- `General.AddressData.*` beyond country and currency
- `General.Listings.*` cross-listings (record primary exchange only)

## Core design principles

These five principles drive every architectural decision below. Read them
before designing any table, query, or screen.

### 1. Cadence-aware storage
Data fields update on four different clocks: static, quarterly, event-driven,
and daily forward-looking. Do not collapse them into one wide row per ticker
per day. Each cadence gets its own table; joins compose them at query time.
Storing everything daily wastes 99%+ of the bytes and obscures what actually
changed.

### 2. Point-in-time integrity (no look-ahead bias)
Every historical computation must reflect what was actually knowable on the
date in question. Quarterly fundamentals are knowable as of their
`report_date` (which we source from the vendor's `filing_date` field),
**not** their fiscal period end. Analyst estimates and ratings are knowable
only on dates they were snapshotted. Code that joins fundamentals or
estimates to historical prices must use the appropriate "becomes-known"
timestamp.

### 3. Derive, don't store
Anything computable from price + shares outstanding + fundamentals (market
cap, trailing multiples, moving averages, beta, 52-week ranges) is computed
on demand or materialized as a view. We do not persist derived values that
could silently disagree with their inputs.

### 4. Snapshot only forward-looking data
Forward-looking values (analyst ratings, target prices, forward EPS
estimates, revenue estimates per future period) cannot be reconstructed from
history. These — **and only these** — are captured in an append-only daily
snapshot.

### 5. FX-aware from day 1
MVP universes will be US-listed, but every monetary field is stored in its
native currency with a currency code attached. An FX rate table allows
USD-equivalent presentation. This avoids a painful retrofit when non-US
tickers are added.

## Vendor

The vendor is **EODHD** (eodhd.com). API key lives in `.env`
(`EODHD_API_TOKEN=...`) and is read at startup. The two endpoints used:

- **Fundamentals**: `/api/fundamentals/<ticker>` — returns the JSON described
  below.
- **Prices**: `/api/eod/<ticker>` (with `from=...&period=d`) — returns a flat
  array of daily OHLCV records.

EODHD-specific quirks to honor in the parser:
- Many numeric fields are returned as JSON strings (e.g., `Earnings.Trend`
  growth values like `"0.0944"`). Parse to `Decimal` or `float` as
  appropriate.
- Statement field names are camelCase (`totalAssets`, `freeCashFlow`,
  `commonStockSharesOutstanding`). We normalize to snake_case in the
  warehouse — the parser is the only layer that knows the vendor field
  names.
- The financials block uses `date` for fiscal period end and `filing_date`
  for the report date. The `Earnings.History` block uses `reportDate` for
  the same concept. Both map to `report_date` in our schema.

## Ingestion model

The vendor returns two files per ticker:

- **Fundamentals file** (`<ticker>.json`, ~100 KB–1.5 MB) containing
  `General`, `Highlights`, `Valuation`, `SplitsDividends`, `AnalystRatings`,
  `outstandingShares`, `Earnings`, and `Financials` (the full quarterly and
  annual statements).
- **Price file** (~1.5 MB for a 45-year history) — a flat array of
  `{date, open, high, low, close, adjusted_close, volume}` records.

We **redownload both files in full every day**. Bandwidth and disk are cheap
relative to the engineering cost of incremental, partial, or section-aware
API calls. EODHD cannot easily be queried for "just what changed," so we
don't try.

This makes ingestion logic the central design question: a single input file
fans out to many tables with different write semantics. Get this right and
the rest of the system follows.

### Per-section ingestion semantics

| Source section / field | Target table | Write mode |
|---|---|---|
| `General.*` | `security_master` | UPSERT by `ticker`; latest wins |
| `Financials.Balance_Sheet.quarterly` | `balance_sheet` | UPSERT by `(ticker, fiscal_period_end)`; `report_date` from `filing_date`; `loaded_at` for restatements |
| `Financials.Income_Statement.quarterly` | `income_statement` | UPSERT by `(ticker, fiscal_period_end)`; `loaded_at` |
| `Financials.Cash_Flow.quarterly` | `cash_flow` | UPSERT by `(ticker, fiscal_period_end)`; `loaded_at` |
| `Highlights.*` (TTM/MRQ aggregates) | `quarterly_fundamentals` | UPSERT by `(ticker, mrq_period_end)`; `loaded_at` |
| `Earnings.History` | `earnings_events` | UPSERT by `(ticker, fiscal_period_end)`; `loaded_at` |
| `outstandingShares.quarterly` | `shares_outstanding` | UPSERT by `(ticker, period_end)` |
| `SplitsDividends.NumberDividendsByYear` | `dividends_annual` | UPSERT by `(ticker, year)` |
| `SplitsDividends.{ForwardAnnualDividendRate, DividendDate, ExDividendDate, ...}` | `dividends_declared` | UPSERT by `(ticker, ex_date)` |
| `SplitsDividends.{LastSplitFactor, LastSplitDate}` | `splits` | UPSERT by `(ticker, split_date)` |
| `AnalystRatings.*` + `Highlights.EPSEstimate*` | `daily_forward_snapshot` | **APPEND** row with `snapshot_date = today` |
| `Earnings.Trend` (per future period) | `analyst_estimates_history` | **APPEND** row with `snapshot_date = today` |
| Price file: `close`, `open`, `high`, `low`, `volume` | `prices_daily` | UPSERT by `(ticker, date)` |
| Price file: `adjusted_close` | `prices_daily.adjusted_close` | **REPLACE the entire column** for that ticker on each load (see below) |

Restatement semantics for UPSERT tables: re-ingesting a corrected vendor value
updates the existing natural-key row in place ("latest value wins"). We keep
`loaded_at` to track recency/change timing, but we do not keep multiple
versioned rows per natural key in MVP.

### Adjusted close handling — the one tricky case

The vendor's `adjusted_close` is back-adjusted for **all subsequent** splits
and dividends. The raw OHLC values are NOT — they preserve what the stock
actually traded at on each historical day. We can confirm this with AAPL's
4:1 split on 2020-08-31: the close on 2020-08-28 is 499.23 (the real Friday
price) while its `adjusted_close` is 121.17 (back-adjusted by 4× plus
subsequent dividends).

This means `adjusted_close` is **retroactively mutable**. Every time the
company splits or pays a dividend going forward, every historical
`adjusted_close` value shifts.

The simplest correct approach: on every price load, **overwrite the
`adjusted_close` column for that ticker's entire history** from the vendor
file. The raw OHLC stays put. There's no point trying to store point-in-time
adjusted closes because adjusted close is, by definition, an as-of-today
view.

If a future requirement needs true point-in-time prices (e.g., computing a
strategy's actual return without look-ahead in the adjustment factor), the
right path is to store a corporate-actions table (splits + dividends with
their ex-dates) and re-derive the adjustment factor as of any historical
date. That's strictly a future need; not in MVP.

### Idempotency requirement

Re-running ingestion on the same input files MUST leave the warehouse
byte-identical (modulo `loaded_at` timestamps). This is the property that
makes "re-download everything every day" safe. Every UPSERT must be keyed on
a natural key; every APPEND must be deduped by `(natural_key,
snapshot_date)` so running the daily script twice on the same calendar day
doesn't create duplicate snapshot rows.

### Per-section ingestion modules

Implement one parser-and-writer module per logical section in
`src/ingest/sections/`: `general.py`, `financials.py`, `earnings.py`,
`shares.py`, `dividends.py`, `analyst_snapshot.py`, `prices.py`. A single
top-level `ingest_ticker(ticker)` orchestrator opens the two files and calls
each section module. A failure in one section logs and skips that section;
the rest of the ticker still loads.

## Universe management

The set of actively-followed tickers lives in a `universe` table in the
warehouse, **not** in `config/universe.yml`. The YAML file exists only as a
**seed** for initial setup — `scripts/seed_universe.py` reads it and inserts
rows.

The function `add_ticker(con, ticker, notes=None)` in `src/universe.py` does
two things:

1. Calls `fetch_and_ingest(con, ticker)` to validate the ticker against EODHD
   and backfill all historical data (statements, earnings events, dividends,
   price history, etc.). If EODHD rejects the ticker, this raises and the
   universe row is never written.
2. Upserts a row into `universe` with `added_at = now()`, `active = true`.

The canonical ticker argument passed to `add_ticker` (e.g. `7203.TSE`) is
preserved as the warehouse key — it is **not** replaced by `General.Code` from
the vendor response (which for non-US symbols is the bare symbol without the
exchange suffix).

The newly-added ticker has every panel populated immediately **except** the
analyst-revision screens (Phase 8), which depend on accumulated daily
forward snapshots. Those screens will produce signal for that ticker only
after ~30 days of snapshot history.

Removing a ticker is a soft delete (`active = false`); the historical data
stays so screens can run on full universes including delisted/removed names
when desired.

Both the CLI (`scripts/add_ticker.py AAPL`) and the Streamlit universe page
call the same `add_ticker()` function. The CLI exists from Phase 3; the UI
page from Phase 5.

## Tech stack

- **Language**: Python 3.11+
- **Storage**: DuckDB (single-file analytical database with `ASOF JOIN`,
  fast aggregations, and native Parquet I/O).
- **ETL**: pandas for the small per-ticker JSON parsing; polars for any
  query-side work that joins price history against fundamentals at scale.
- **UI (MVP)**: Streamlit.
- **HTTP**: httpx (sync) with simple retry/backoff.
- **Testing**: pytest. Any function involving date lagging, point-in-time
  joins, or restatement handling MUST have tests with explicit fixture dates.
- **Dependency management**: uv (preferred) or poetry.
- **Linting / formatting**: ruff + black.
- **Configuration**: `.env` via `python-dotenv` for the EODHD API key;
  `config/settings.yml` for non-secret paths and toggles.

## Repository layout

```
.
├── AGENTS.md               # this file
├── PLAN.md                 # phased implementation plan
├── README.md               # quick start for humans
├── pyproject.toml
├── .env.example            # documents EODHD_API_TOKEN; real .env is gitignored
├── config/
│   ├── universe.yml        # SEED list (~10 names); not source of truth at runtime
│   └── settings.yml        # paths, FX base currency, archive retention
├── data/
│   ├── raw/
│   │   ├── fundamentals/   # <ticker>.json, replaced daily
│   │   └── prices/         # <ticker>.json, replaced daily
│   ├── archive/            # optional: dated copies of raw files for audit
│   └── warehouse.duckdb    # the local database
├── src/
│   ├── universe.py         # add_ticker(), remove_ticker(), list_universe()
│   ├── ingest/
│   │   ├── sections/       # one module per JSON section (see above)
│   │   ├── fetch.py        # EODHD client (rate limiting, retry)
│   │   └── orchestrator.py # ingest_ticker(), ingest_universe()
│   ├── schema/             # DuckDB DDL, migrations
│   ├── compute/            # TTM aggregations, trailing multiples, technicals
│   ├── screens/            # named screen queries
│   └── app/                # Streamlit pages and query layer
├── tests/
│   ├── fixtures/           # sample vendor JSON, mini price history
│   └── ...
└── scripts/
    ├── load_daily.py       # entry point: fetch + ingest universe
    ├── rebuild.py          # full rebuild from raw data (no re-fetch)
    ├── seed_universe.py    # read config/universe.yml -> universe table
    └── add_ticker.py       # CLI wrapper around add_ticker()
```

## Data model summary

Core tables; see `src/schema/` for full DDL.

| Table | Grain | Cadence | Notes |
|---|---|---|---|
| `universe` | one row per followed ticker | user-managed | `ticker`, `added_at`, `active`, optional `notes` |
| `security_master` | one row per ticker | static | identifiers, sector, GIC codes, fiscal year end, currency, `is_delisted` |
| `quarterly_fundamentals` | ticker × MRQ end | quarterly | aggregates from `Highlights`; carries `mrq_period_end`, `loaded_at` |
| `income_statement`, `balance_sheet`, `cash_flow` | ticker × fiscal quarter | quarterly | full statements (34 / 64 / 32 columns respectively); `report_date` is the point-in-time key; `loaded_at` for restatements |
| `earnings_events` | ticker × fiscal quarter | event | report date, EPS estimate, EPS actual, surprise % |
| `shares_outstanding` | ticker × as-of date | quarterly | from `outstandingShares.quarterly` |
| `dividends_declared` | ticker × ex-date | event | declared rate, ex-date, pay-date |
| `dividends_annual` | ticker × year | annual | DPS history from `NumberDividendsByYear` |
| `splits` | ticker × split date | event | factor (`4:1` etc.) |
| `daily_forward_snapshot` | ticker × snapshot date | daily | analyst ratings breakdown, target price, forward EPS estimates per period |
| `analyst_estimates_history` | ticker × snapshot date × future period | daily | the per-period detail from `Earnings.Trend` |
| `prices_daily` | ticker × trading date | daily | OHLCV in native currency; `adjusted_close` re-derived each load |
| `fx_rates_daily` | currency × date | daily | rate to USD |

Derived (materialized views or computed at query time, never persisted as
authoritative tables):
- `ttm_eps`, `ttm_revenue`, `ttm_ebitda` (4-quarter rolling sums of actuals)
- `trailing_multiples_daily` (price × shares ÷ TTM metric, joined with
  appropriate lag)
- `technicals_daily` (MAs, 52W range, beta, realized volatility)

### A note on statement column counts

EODHD returns 64 balance-sheet, 34 income-statement, and 32 cash-flow fields
per period. We store **all of them**, normalized to snake_case, rather than
curating a subset. Disk is free and which fields any given screen wants is
hard to predict. The parser is the only thing that needs to know about the
camelCase vendor names; downstream code reads only snake_case.

## Conventions

- **Primary identifier**: `ticker` (e.g., `AAPL`). For non-US, use the vendor
  format (`AAPL.US`, `7203.TSE`, etc.). Persist the original `Code` and
  `Exchange` separately.
- **Dates**: ISO 8601 (`YYYY-MM-DD`) in storage. Timestamps in UTC.
- **Currency**: every monetary column lives in a table with a `currency`
  column, OR has a sibling `_ccy` column. Never assume USD.
- **Nulls**: use SQL `NULL`, not sentinel values. The vendor frequently emits
  `null` (e.g., `SharesShort`, EPS actuals for future dates, BS fields for
  non-applicable line items); map directly.
- **Schema changes**: append-only migration scripts in
  `src/schema/migrations/` with a leading numeric prefix. Never edit a past
  migration.
- **`loaded_at` everywhere**: every UPSERT-mode table has a `loaded_at` UTC
  timestamp. UPSERT writes latest values in place on the natural key; we use
  `loaded_at` to detect recency and potential restatement timing, not to keep
  versioned history rows.
- **Decimal handling**: prefer DuckDB `DECIMAL(p,s)` for per-share figures
  where rounding matters; `DOUBLE` is fine for ratios and large aggregates.
- **Field naming**: camelCase from EODHD → snake_case in DuckDB. The mapping
  lives in `src/ingest/sections/` modules, not in the schema.

## Anti-patterns and pitfalls

Things to **NOT do**, learned from the design conversation:

- **Do not trust EODHD 200 responses blindly.** A successful HTTP 200 can
  carry `{"Error": "Ticker Not Found."}`. `fetch_fundamentals()` and
  `fetch_prices()` validate the response shape and raise `ValueError` before
  returning; do not bypass this check or return raw responses to callers
  who assume they are well-formed.
- **Do not hard-code or use CWD-relative warehouse paths in scripts.** Use
  `runner.warehouse_path()`, which reads from `config/settings.yml` and
  returns an absolute path. A CWD-relative default (`"data/warehouse.duckdb"`)
  will silently point at a different file when a script is run from outside
  the project root.
- **Do not use `use_container_width=True` in Streamlit.** The parameter was
  deprecated in Streamlit 1.35+ and removed in 1.57+. Use `width="stretch"`
  (the equivalent for full-container width) or `width="content"` for
  auto-sizing.
- **Do not store vendor-computed multiples** (`Valuation.TrailingPE`,
  `Highlights.MarketCapitalization`, `Highlights.PERatio`, etc.) for
  historical purposes. Compute them. They go stale, can disagree with the
  inputs, and confuse audits.
- **Do not lag fundamentals by `fiscal_period_end`**. Use `report_date`
  (sourced from EODHD's `filing_date`). A December-quarter result reported
  on January 30 was not knowable in December.
- **Do not try to incrementally fetch or merge prices.** Always pull the
  full series and let UPSERT-by-(ticker, date) plus full-column-replace on
  `adjusted_close` do the work. Trying to be clever about "only fetch since
  last load" loses correctness on retroactive adjustments.
- **Do not use raw `close` for split-spanning return calculations or
  long-window valuation history.** Use `adjusted_close`. Raw close exists so
  point-in-time multiples can be computed against point-in-time share
  counts, but for charting and most computations `adjusted_close` is right.
- **Do not overwrite historical snapshot rows** when the vendor revises a
  number. Append; treat the highest `loaded_at` as current.
- **Do not silently drop tickers** that delist or get acquired. Set
  `is_delisted = true`, keep their warehouse history, and use `universe.active`
  to control current screens.
- **Do not let a single failing ticker break the daily load**. Per-ticker
  and per-section errors are logged; the rest of the universe proceeds.
- **Do not call vendor APIs from the UI layer**. The UI reads only from
  DuckDB. ETL is a separate process. The one exception is `add_ticker()`,
  which by design needs to make a vendor call to validate and backfill.
- **Do not store anything derived from analyst forecasts as if it were
  fundamental**. Forward P/E, PEG, target-implied return — these are
  snapshot-time observations, not facts about the company.
- **Do not commit `.env`**. Use `.env.example` for documentation; `.env` is
  in `.gitignore`.
- **Do not use `is` as a SQL table alias in DuckDB**. It is a reserved
  keyword and the query will fail with a parser error. Use `stmt`, `s`, or
  any other non-reserved alias for `income_statement`.
- **Do not use `PERCENT_RANK() WITHIN GROUP (ORDER BY ...)` in DuckDB**.
  That is PostgreSQL ordered-set aggregate syntax. DuckDB's `PERCENT_RANK()`
  is a window function only. Compute percentile ranks in Python from a
  fetched DataFrame instead.
- **Do not use `pd.DataFrame.applymap()`**. It was removed in pandas 2.1;
  use `.map()` for element-wise operations on DataFrames.
- **Do not forget `load_dotenv()` in Streamlit pages that trigger EODHD
  API calls**. Streamlit does not inherit shell environment variables the
  same way scripts do. Call `load_dotenv()` at the top of any page that
  calls `add_ticker()` or any fetch function.

## Shell execution rules

- **Never run `python -c "..."` (or `uv run python -c "..."`) with inline
  Python that contains `#` comments.** The shell treats `#` as a comment
  delimiter inside double-quoted strings on some configurations, which
  silently truncates the script and causes the command to fail or hang.
  Instead, write a small temporary `.py` file and run it with
  `uv run python <file>`, or use a heredoc:
  ```bash
  uv run python - <<'EOF'
  # comments are safe here
  print("hello")
  EOF
  ```

## Build / test commands

Confirmed interface (as of Phase 6):

```bash
uv sync                                  # install deps
uv run pytest                            # run tests
uv run ruff check . && uv run black --check .   # lint + format check
uv run python scripts/load_daily.py      # fetch + ingest universe
uv run python scripts/rebuild.py         # full rebuild from raw (no fetch)
uv run python scripts/add_ticker.py AAPL # add a ticker and backfill
uv run streamlit run src/app/Home.py     # launch dashboard
```

## Working with the data: sample query pattern

The most-repeated pattern in this codebase is the point-in-time join between
prices, shares outstanding, and quarterly fundamentals. DuckDB's `ASOF JOIN`
makes it readable:

```sql
-- Trailing P/E for every (ticker, date) using only data known on that date.
SELECT
    p.ticker,
    p.date,
    p.adjusted_close,
    ttm.ttm_eps,
    p.adjusted_close / NULLIF(ttm.ttm_eps, 0) AS trailing_pe
FROM prices_daily p
ASOF LEFT JOIN ttm_eps ttm
    ON p.ticker = ttm.ticker
   AND p.date  >= ttm.report_date
WHERE p.ticker IN (SELECT ticker FROM universe WHERE active);
```

The `>=` on `report_date` (not `fiscal_period_end`) is the entire point of
principle #2. We use `adjusted_close` here so the historical series is
consistent across splits — and the EPS coming out of `ttm_eps` is
split-adjusted on the same basis because `Earnings.History` EPS values are
already reported on a split-adjusted basis. The `universe` join is the
standard way to scope a screen to currently-followed names.

## Phase 4 decisions (resolved open questions)

### Beta benchmark: SPY only

SPY is loaded into `prices_daily` like any other ticker. To get beta computed
in `technicals_daily`, run `add_ticker(con, "SPY")` once (or include it in
`config/universe.yml` seed if desired). Beta is NULL for all dates where
`prices_daily` has no 'SPY' row. Per-region benchmarks are deferred to Phase 10.

### Net debt formula

`long_term_debt_total + short_term_debt - cash_and_short_term_investments`
(COALESCE to 0 for missing components). See `src/compute/multiples.py`.

### Derived views live in Python, not in migrations

TTM, multiples, and technicals views are created via `src/compute/ttm.py`,
`src/compute/multiples.py`, and `src/compute/technicals.py` using
`CREATE OR REPLACE VIEW`. `schema/runner.py::open_db()` calls
`compute.setup_views(con)` after migrations so every connection has the views.
No migration file is needed for views — they are code, not schema state.

### `add_ticker` ordering fix

As of Phase 4, `add_ticker` writes a pending `active=false` universe row
**before** ingest begins so warehouse data is always traceable. On ingest
failure for a brand-new ticker the pending row is removed, keeping the
universe clean. Notes are updated when explicitly re-provided on re-add.

## Phase 5 decisions (resolved open questions)

### TTM timing unified to `earnings_events.report_date`

All four TTM views (`ttm_eps`, `ttm_revenue`, `ttm_ebitda`, `ttm_fcf`) now
source `report_date` from `earnings_events` by joining on
`(ticker, fiscal_period_end)`. The initial implementation of `ttm_revenue`,
`ttm_ebitda`, and `ttm_fcf` used the statement table's own `filing_date`,
which diverged from `ttm_eps` (which always used `earnings_events`). Unified
to prevent cross-multiple timing drift around earnings windows.

Tests for revenue/EBITDA/FCF TTM now require `earnings_events` rows for the
same fiscal periods — the join is inner-equivalent on `report_date IS NOT NULL`.

### Beta benchmark ticker from settings

`technicals_daily` reads `config/settings.yml → benchmark.ticker` at view
creation time (`src/compute/technicals.py`). The ticker is injected into the
SQL string, so changing the config and reconnecting updates the view.
Default: `SPY.US`. Hardcoding `'SPY'` would silently produce NULL beta
because EODHD uses the `.US` suffix convention.

### `queries.py` layer: SQL and DataFrame computations

`src/app/queries.py` is the single place for all data access. This includes
both SQL queries (functions that take a `DuckDBPyConnection`) and pure
DataFrame computations that are better expressed in Python (e.g.
`valuation_stats`, which computes percentile rank from a fetched history
DataFrame). Page files call only `queries.*` — no SQL or pandas aggregation
in pages.

### `matplotlib` required for `background_gradient`

`pandas.Styler.background_gradient` requires matplotlib as a backend for
color mapping. Added `matplotlib` to `[dependencies]` in `pyproject.toml`.
Omitting it causes a hard `ImportError` at render time, not at import.

## Phase 6 decisions (resolved open questions)

### EODHD error responses validated at the fetch layer

`fetch_fundamentals()` and `fetch_prices()` now validate the vendor response
before returning it to callers:

- A response dict containing an `"Error"` key (EODHD's 200-style error format,
  e.g., `{"Error": "Ticker Not Found."}`) raises `ValueError` immediately.
- A fundamentals response missing `General.Code` raises `ValueError` — this
  catches truncated or malformed payloads that would otherwise silently ingest
  empty data.
- A prices response that is not a JSON array raises `ValueError`.

Per-section error swallowing in `ingest_ticker()` is still in place for the
daily refresh path (a corrupted section should not abort other sections).
However, `fetch_and_ingest()` now fails fast on the fetch itself, which means
`add_ticker()` cannot activate a ticker when EODHD returns a plausible-looking
but invalid payload.

### Warehouse path centralized in `src/schema/runner.py`

`runner.warehouse_path()` returns the absolute warehouse path from
`config/settings.yml`, with `WAREHOUSE_PATH` env var as an explicit override.
All three CLI scripts (`load_daily.py`, `add_ticker.py`, `seed_universe.py`)
call `warehouse_path()` instead of defaulting to a CWD-relative string. This
guarantees that ETL scripts and the Streamlit app always point at the same
database file, regardless of the working directory from which a script is run
or how cron invokes it.

### Snapshot coverage on Universe management page

`queries.snapshot_coverage()` returns a per-active-ticker summary: first/last
snapshot date and total days collected. The Universe management page exposes
this as a table so ingestion gaps are visible at a glance. Forward-looking
screens (Phase 11) require ≥ 30 days of snapshot history per ticker.

### `next_period_end` replaces `next_earnings`

The Deep Dive header field and query column previously named `next_earnings`
has been renamed to `next_period_end` throughout `queries.py` and the page.
The metric label on the Deep Dive header is now "Next Period End". This
accurately reflects the source field (`earnings_events.fiscal_period_end`),
which is the end of the upcoming fiscal quarter, not the actual report date.

### Streamlit width API

`use_container_width=True` was deprecated in Streamlit 1.35+ and replaced by
`width="stretch"` (which is also the default for most layout-aware components).
All `st.plotly_chart`, `st.dataframe`, and related calls now use
`width="stretch"` explicitly rather than the deprecated parameter.

## When in doubt

- Prefer adding a test over adding a comment.
- Prefer a materialized view over a stored derived column.
- Prefer raising a question in PLAN.md "open questions" over making an
  undocumented decision.
- Prefer breaking up a phase if it gets too large; the phase boundaries in
  PLAN.md exist to keep deliverables shippable.
