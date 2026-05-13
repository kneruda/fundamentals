# AGENTS.md

> Guidance for AI coding agents (and humans) working on this project.
> If a `CLAUDE.md` is desired, make it a symlink or short pointer to this file
> so the two never drift.

## Mission

Build a personal equity fundamentals dashboard that tracks valuation,
profitability, growth, balance-sheet strength, and analyst expectations for a
user-managed universe of stocks. The dashboard supports four modes:

1. **Universe management** — add or remove tickers through a simple UI; new
   tickers backfill all available historical data immediately. Bulk loads
   of hundreds of tickers run from a single command.
2. **Drill-down** on a single ticker, with full statements (quarterly and
   annual, summary or full, in configurable units), historical multiples,
   and analyst expectations in one view.
3. **Screens** that filter the whole universe on configurable criteria —
   trailing fundamentals, relative-to-history valuation, vendor-provided
   forward estimate trends, and (once enough snapshot history accumulates)
   our own forward-looking rating-change signals.
4. **Watchlists / portfolios** — named subsets of the universe (created
   manually, from file, or saved from a screen result) that scope the
   *display* of every screen while leaving the *comparison universe*
   (medians, percentiles, sector aggregates) anchored to the full active
   universe.

## Scope

### In scope
- A managed universe of equities (table-backed, user-editable through UI/CLI)
- Static company data (identifiers, sector classification, fiscal year end,
  currency, country)
- Quarterly **and annual** fundamentals (TTM/MRQ aggregates from the vendor
  `Highlights` block; full statements from the `Financials` block — both
  `.quarterly` and `.yearly`)
- Full financial statements (income statement, balance sheet, cash flow)
- Earnings events (estimates, actuals, surprises, report dates)
- Dividend events and annual history
- Analyst expectations (consensus rating, target price, forward EPS estimates
  per future fiscal period, plus vendor-provided 7/30/60/90-day trend deltas)
- Daily price history from the vendor (separate endpoint, same vendor)
- FX rates (USD is the reporting currency; design supports non-USD tickers)
- Watchlists with optional share-count and cost-basis columns for portfolio
  use (schema reserved from Phase 10; calculations later)

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

These principles drive every architectural decision below. Read them
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
cap, trailing multiples, moving averages, beta, 52-week ranges, portfolio
values) is computed on demand or materialized as a view. We do not persist
derived values that could silently disagree with their inputs.

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

### 6. Display set ≠ comparison set
Filtering which tickers a user *sees* (a watchlist, a screen result) is a
separate concern from defining the *comparison universe* against which
medians, percentiles, and sector aggregates are computed. The comparison
universe is always the full active universe (or a country-scoped subset
when that future enhancement lands). A 3-stock watchlist does not redefine
the meaning of "median sector P/E."

### 7. Shared utilities prevent semantic drift
When two flows accept the same kind of input (e.g., a list of tickers
typed by a user or uploaded as a file), they share the same parser. When
two screens compute the same derived metric, they share the same query
function. Duplication invites the two copies to drift apart, and the
drift is usually invisible until something surprising happens at the UI.

## Vendor

The vendor is **EODHD** (eodhd.com). API key lives in `.env`
(`EODHD_API_TOKEN=...`) and is read at startup. The two endpoints used:

- **Fundamentals**: `/api/fundamentals/<ticker>` — returns the JSON described
  below.
- **Prices**: `/api/eod/<ticker>` (with `from=...&period=d`) — returns a flat
  array of daily OHLCV records.

EODHD-specific quirks to honor in the parser:
- Many numeric fields are returned as JSON strings (e.g., `Earnings.Trend`
  growth values like `"0.0944"`, and the `eps_trend_*` / `revisions_*`
  fields used by Phase 13 forward screens). Parse to `Decimal` or `float`
  as appropriate.
- Statement field names are camelCase (`totalAssets`, `freeCashFlow`,
  `commonStockSharesOutstanding`). We normalize to snake_case in the
  warehouse — the parser is the only layer that knows the vendor field
  names.
- The financials block uses `date` for fiscal period end and `filing_date`
  for the report date. The `Earnings.History` block uses `reportDate` for
  the same concept. Both map to `report_date` in our schema.
- The `Financials.*.quarterly` and `Financials.*.yearly` arrays carry the
  same field names and shapes; only the period type and the values differ.
  The parser ingests both with a single mapping function plus a
  `period_type` discriminator.

A successful HTTP 200 can carry `{"Error": "..."}`. Validate response shape
in the fetch layer before returning to callers.

## Ingestion model

The vendor returns two files per ticker:

- **Fundamentals file** (`<ticker>.json`, ~100 KB–1.5 MB) containing
  `General`, `Highlights`, `Valuation`, `SplitsDividends`, `AnalystRatings`,
  `outstandingShares`, `Earnings`, and `Financials` (quarterly *and*
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
| `Financials.Balance_Sheet.{quarterly,yearly}` | `balance_sheet` | UPSERT by `(ticker, fiscal_period_end, period_type)`; `report_date` from `filing_date`; `loaded_at` |
| `Financials.Income_Statement.{quarterly,yearly}` | `income_statement` | UPSERT by `(ticker, fiscal_period_end, period_type)`; `loaded_at` |
| `Financials.Cash_Flow.{quarterly,yearly}` | `cash_flow` | UPSERT by `(ticker, fiscal_period_end, period_type)`; `loaded_at` |
| `Highlights.*` (TTM/MRQ aggregates) | `quarterly_fundamentals` | UPSERT by `(ticker, mrq_period_end)`; `loaded_at` |
| `Earnings.History` | `earnings_events` | UPSERT by `(ticker, fiscal_period_end)`; `loaded_at` |
| `outstandingShares.quarterly` | `shares_outstanding` | UPSERT by `(ticker, period_end)` |
| `SplitsDividends.NumberDividendsByYear` | `dividends_annual` | UPSERT by `(ticker, year)` |
| `SplitsDividends.{ForwardAnnualDividendRate, DividendDate, ExDividendDate, ...}` | `dividends_declared` | UPSERT by `(ticker, ex_date)` |
| `SplitsDividends.{LastSplitFactor, LastSplitDate}` | `splits` | UPSERT by `(ticker, split_date)` |
| `AnalystRatings.*` + `Highlights.EPSEstimate*` | `daily_forward_snapshot` | **APPEND** row with `snapshot_date = today` |
| `Earnings.Trend` (per future period, including vendor `*7daysAgo` / revisions counts) | `analyst_estimates_history` | **APPEND** row with `snapshot_date = today` |
| Price file: `close`, `open`, `high`, `low`, `volume` | `prices_daily` | UPSERT by `(ticker, date)` |
| Price file: `adjusted_close` | `prices_daily.adjusted_close` | **REPLACE the entire column** for that ticker on each load |
| Per-ticker outcome (every load attempt) | `load_runs` | APPEND row with start/finish, status, error |

Restatement semantics for UPSERT tables: re-ingesting a corrected vendor
value updates the existing natural-key row in place ("latest value wins").
We keep `loaded_at` to track recency and potential restatement timing, but
we do not keep multiple versioned rows per natural key in MVP.

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

### Rate limiting and bulk ingestion

The throttle lives in `src/ingest/fetch.py` (or a thin wrapper). All EODHD
calls go through it. Configuration in `config/settings.yml` under
`eodhd.rate_limit`. Default conservative until the subscription tier is
confirmed. Per-ticker retries with exponential backoff on transient HTTP
errors. 200-with-Error responses are terminal (no retry — the vendor is
telling us the ticker is bad).

Bulk loads of 500+ tickers run through `scripts/bulk_load.py` (Phase 9
onward), backed by the `bulk_load_jobs` checkpoint table. Resumable across
restarts. See "Phase 9 decisions" below.

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
preserved as the warehouse key — it is **not** replaced by `General.Code`
from the vendor response (which for non-US symbols is the bare symbol
without the exchange suffix).

The newly-added ticker has every panel populated immediately **except** the
rating-change forward screens (Phase 13B), which depend on accumulated
daily forward snapshots. Those produce signal for that ticker only after
~30 days of snapshot history. The EPS/revenue revision screens (Phase 13A),
in contrast, work on day 1 because EODHD pre-computes 7/30-day deltas.

Removing a ticker is a soft delete (`active = false`); the historical data
stays so screens can run on full universes including delisted/removed names
when desired.

Both the CLI (`scripts/add_ticker.py AAPL`) and the Streamlit universe page
call the same `add_ticker()` function. Bulk loads use
`bulk_add_tickers(con, tickers)` which wraps `add_ticker` with rate
limiting, retry, and the `bulk_load_jobs` checkpoint table.

## Watchlists and portfolios

Watchlists are named subsets of the universe. They serve two related
purposes:

1. **Scoping a view.** Selecting an active watchlist filters the rows
   shown on every screen (Home table, Screens, Sectors, Forward Screens).
   Comparisons (medians, percentiles, sector aggregates) remain anchored
   to the full active universe per principle #6.
2. **Recording a portfolio.** The `watchlist_membership` table includes
   nullable `shares` and `cost_basis` columns. If populated, future phases
   can compute position values, weights, gains/losses against
   `prices_daily.adjusted_close`. The Phase 10 deliverable does *not*
   include those calculations; the schema only reserves the columns.

Watchlists are **snapshot**, not dynamic. A watchlist created from a screen
result freezes the ticker list at save time. To refresh, re-save from the
current screen result. A "rebuild from saved filter parameters" capability
is future work.

Watchlist creation accepts manual entry, file upload, or "save current
screen result." The first two paths share the same input parser
(`src/ticker_input.py`) as bulk universe upload — see principle #7.

## Tech stack

- **Language**: Python 3.11+
- **Storage**: DuckDB (single-file analytical database with `ASOF JOIN`,
  fast aggregations, and native Parquet I/O). One writer at a time —
  scheduling and concurrency considerations are real and addressed in
  Phase 9.
- **ETL**: pandas for the small per-ticker JSON parsing; polars for any
  query-side work that joins price history against fundamentals at scale.
- **UI (MVP)**: Streamlit. `st.dialog` for modal drill-downs (Phase 12).
- **HTTP**: httpx (sync) with simple retry/backoff and a single shared
  rate limiter for EODHD calls.
- **Containerization**: Docker + docker-compose. One image, two services
  (`app` for one-shot scripts, `streamlit` for the long-running UI). See
  Phase 9 decisions.
- **Scheduling**: local cron (or `systemd` timers) calling
  `docker compose run --rm app uv run python scripts/load_daily.py`.
  Designed to migrate cleanly to EC2.
- **Testing**: pytest. Any function involving date lagging, point-in-time
  joins, restatement handling, or display-vs-comparison-set distinction
  MUST have tests with explicit fixture dates and ticker sets.
- **Dependency management**: uv (preferred) or poetry.
- **Linting / formatting**: ruff + black.
- **Configuration**: `.env` via `python-dotenv` for the EODHD API key;
  `config/settings.yml` for non-secret paths, rate limits, benchmark
  ticker, archive retention, and other toggles.

## Repository layout

```
.
├── AGENTS.md               # this file
├── PLAN.md                 # phased implementation plan
├── README.md               # quick start for humans
├── Dockerfile              # Phase 9
├── docker-compose.yml      # Phase 9: app + streamlit services
├── Makefile                # Phase 9: shortcuts (make load, make ui, make shell)
├── pyproject.toml
├── .env.example            # documents EODHD_API_TOKEN; real .env is gitignored
├── config/
│   ├── universe.yml        # SEED list (~10 names); not source of truth at runtime
│   └── settings.yml        # paths, FX base currency, archive retention, rate limits, benchmark
├── data/
│   ├── raw/
│   │   ├── fundamentals/   # <ticker>.json, replaced daily
│   │   └── prices/         # <ticker>.json, replaced daily
│   ├── archive/            # optional: dated copies of raw files for audit
│   ├── logs/               # cron + bulk-load logs
│   └── warehouse.duckdb    # the local database
├── src/
│   ├── universe.py         # add_ticker(), remove_ticker(), list_universe()
│   ├── watchlist.py        # Phase 10: create/delete/list/get_membership
│   ├── ticker_input.py     # Phase 9: shared parser (textarea + file)
│   ├── ingest/
│   │   ├── sections/       # one module per JSON section
│   │   ├── fetch.py        # EODHD client (rate limiting, retry)
│   │   ├── bulk.py         # Phase 9: bulk_add_tickers with checkpointing
│   │   └── orchestrator.py # ingest_ticker(), ingest_universe()
│   ├── schema/             # DuckDB DDL, migrations
│   ├── compute/            # TTM aggregations, trailing multiples, technicals
│   ├── screens/
│   │   ├── trailing.py     # Phase 7
│   │   ├── sectors.py      # Phase 8
│   │   ├── forward_vendor.py  # Phase 13A
│   │   └── forward_history.py # Phase 13B
│   └── app/                # Streamlit pages and query layer
├── tests/
│   ├── fixtures/           # sample vendor JSON, mini price history
│   └── ...
└── scripts/
    ├── load_daily.py       # entry point: fetch + ingest universe
    ├── rebuild.py          # full rebuild from raw data (no re-fetch)
    ├── seed_universe.py    # read config/universe.yml -> universe table
    ├── add_ticker.py       # CLI wrapper around add_ticker()
    ├── bulk_load.py        # Phase 9: rate-limited resumable bulk load
    └── cron.example        # Phase 9: sample crontab entry
```

## Data model summary

Core tables; see `src/schema/` for full DDL.

| Table | Grain | Cadence | Notes |
|---|---|---|---|
| `universe` | one row per followed ticker | user-managed | `ticker`, `added_at`, `active`, optional `notes` |
| `security_master` | one row per ticker | static | identifiers, sector, GIC codes, fiscal year end, currency, country, `is_delisted` |
| `quarterly_fundamentals` | ticker × MRQ end | quarterly | aggregates from `Highlights`; `mrq_period_end`, `loaded_at` |
| `income_statement`, `balance_sheet`, `cash_flow` | ticker × fiscal period × period_type | quarterly + annual | full statements (34 / 64 / 32 columns); `report_date` is the point-in-time key; `period_type` ∈ {'quarterly', 'annual'}; `loaded_at` |
| `earnings_events` | ticker × fiscal quarter | event | report date, EPS estimate, EPS actual, surprise % |
| `shares_outstanding` | ticker × as-of date | quarterly | from `outstandingShares.quarterly` |
| `dividends_declared` | ticker × ex-date | event | declared rate, ex-date, pay-date |
| `dividends_annual` | ticker × year | annual | DPS history from `NumberDividendsByYear` |
| `splits` | ticker × split date | event | factor (`4:1` etc.) |
| `daily_forward_snapshot` | ticker × snapshot date | daily | analyst ratings breakdown, target price, forward EPS estimates per period |
| `analyst_estimates_history` | ticker × snapshot date × future period | daily | per-period detail from `Earnings.Trend` including vendor `*_7days_ago` / revisions counts |
| `prices_daily` | ticker × trading date | daily | OHLCV in native currency; `adjusted_close` re-derived each load |
| `fx_rates_daily` | currency × date | daily | rate to USD (Phase 14) |
| `watchlist` | one row per named watchlist | user-managed | Phase 10 |
| `watchlist_membership` | watchlist × ticker | user-managed | nullable `shares`, `cost_basis` for portfolio mode |
| `load_runs` | one row per ticker per load attempt | event | Phase 9: status, duration, error message; powers Universe page monitoring |
| `bulk_load_jobs` | one row per ticker per bulk job | event | Phase 9: enables resume |

Derived (materialized views or computed at query time, never persisted as
authoritative tables):
- `ttm_eps`, `ttm_revenue`, `ttm_ebitda`, `ttm_fcf` (4-quarter rolling sums
  of actuals, all timed off `earnings_events.report_date`)
- `trailing_multiples_daily` (price × shares ÷ TTM metric, joined with
  appropriate lag)
- `technicals_daily` (MAs, 52W range, beta, realized volatility)

### A note on statement column counts

EODHD returns 64 balance-sheet, 34 income-statement, and 32 cash-flow fields
per period. We store **all of them**, normalized to snake_case, rather than
curating a subset. Disk is free and which fields any given screen wants is
hard to predict. The parser is the only thing that needs to know about the
camelCase vendor names; downstream code reads only snake_case. The Summary
vs. Full toggle in the Deep Dive Statements panel (Phase 11) is a UI
concept, not a storage decision.

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
  timestamp. UPSERT writes latest values in place on the natural key.
- **Decimal handling**: `DOUBLE` throughout for monetary and per-share
  figures — 15 significant digits is sufficient for this project.
- **Field naming**: camelCase from EODHD → snake_case in DuckDB. The mapping
  lives in `src/ingest/sections/` modules, not in the schema.
- **`period_type`**: lowercase string literals `'quarterly'` and
  `'annual'`. Every query against a statement table filters on
  `period_type` explicitly. `queries.py` helpers always do this.
- **Display set vs. comparison set**: any function in `queries.py` that
  computes a distribution-derived value (median, percentile, sector
  aggregate) accepts an explicit `comparison_set` argument (default None =
  full active universe) separate from any `display_filter`.
- **Pagination**: views over large tables (`prices_daily`, eventually
  `daily_forward_snapshot`) use `queries.<name>_page(...)` helpers with
  `LIMIT`/`OFFSET`. Default page size 100; configurable in the UI.
- **Watchlist names**: case-insensitive uniqueness; stored as
  user-entered, compared lowered.

## Anti-patterns and pitfalls

Things to **NOT do**, learned from the design conversation and from
implementation experience:

- **Do not trust EODHD 200 responses blindly.** A successful HTTP 200 can
  carry `{"Error": "Ticker Not Found."}`. `fetch_fundamentals()` and
  `fetch_prices()` validate the response shape and raise `ValueError` before
  returning; do not bypass this check.
- **Do not hard-code or use CWD-relative warehouse paths in scripts.** Use
  `runner.warehouse_path()`, which reads from `config/settings.yml` and
  returns an absolute path.
- **Do not use `use_container_width=True` in Streamlit.** Use
  `width="stretch"` or `width="content"`.
- **Do not store vendor-computed multiples** (`Valuation.TrailingPE`,
  `Highlights.MarketCapitalization`, etc.) for historical purposes. Compute
  them. They go stale and confuse audits.
- **Do not lag fundamentals by `fiscal_period_end`**. Use `report_date`
  (sourced from EODHD's `filing_date`).
- **Do not try to incrementally fetch or merge prices.** Always pull the
  full series and let UPSERT-by-(ticker, date) plus full-column-replace on
  `adjusted_close` do the work.
- **Do not use raw `close` for split-spanning return calculations.** Use
  `adjusted_close`.
- **Do not overwrite historical snapshot rows** when the vendor revises a
  number. Append; treat the highest `loaded_at` as current.
- **Do not silently drop tickers** that delist or get acquired. Set
  `is_delisted = true`, keep their warehouse history, and use
  `universe.active` to control current screens.
- **Do not let a single failing ticker break the daily load**. Per-ticker
  and per-section errors are logged to `load_runs`; the rest of the
  universe proceeds.
- **Do not call vendor APIs from the UI layer**. The UI reads only from
  DuckDB. ETL is a separate process. The one exception is `add_ticker()`.
- **Do not store anything derived from analyst forecasts as if it were
  fundamental**. Forward P/E, PEG, target-implied return — these are
  snapshot-time observations, not facts about the company.
- **Do not commit `.env`**. Use `.env.example` for documentation.
- **Do not use `is` as a SQL table alias in DuckDB**. Reserved keyword.
- **Do not use `PERCENT_RANK() WITHIN GROUP (ORDER BY ...)` in DuckDB**.
  PostgreSQL-only syntax. DuckDB's `PERCENT_RANK()` is window-only; compute
  in Python from a fetched DataFrame.
- **Do not use `pd.DataFrame.applymap()`**. Removed in pandas 2.1; use
  `.map()`.
- **Do not forget `load_dotenv()` in Streamlit pages that trigger EODHD
  API calls**.
- **Do not apply watchlist filters to median, percentile, or sector
  aggregate calculations.** Per principle #6: display set ≠ comparison
  set. The `comparison_set` argument exists specifically to prevent this.
  Mixing them produces meaningless statistics ("AAPL is the 95th
  percentile of a 3-stock watchlist" — uninformative).
- **Do not reimplement the ticker-input parser.** Bulk universe upload AND
  watchlist creation both call `parse_ticker_input(raw_text)` in
  `src/ticker_input.py`. If parsing semantics need to change, they change
  in one place.
- **Do not run `load_daily.py` and Streamlit against the warehouse
  simultaneously.** DuckDB allows one writer; the load will fail if
  Streamlit holds the file. Default mitigation: schedule loads at quiet
  hours. Alternative: open Streamlit read-only.
- **Do not query statement tables without filtering on `period_type`.**
  Once Phase 11 lands, the same `(ticker, fiscal_period_end)` may have a
  quarterly Q4 row AND an annual row. Queries without the filter
  double-count or join ambiguously. `queries.py` helpers always set
  `period_type`; raw SQL in notebooks must do the same.
- **Do not load all of a ticker's price history into one DataFrame for
  display.** A 45-year series is 11,000+ rows; rendering it in a Streamlit
  table jams the page. Use `queries.prices_page(...)` with `LIMIT`/`OFFSET`.
- **Do not store calculated portfolio values as persistent columns.**
  Current value, weight, gain/loss are derived from
  `watchlist_membership.shares` × `prices_daily.adjusted_close`. Compute on
  demand (principle #3).
- **Do not bake the EODHD rate limit into individual call sites.** The
  throttle lives in `src/ingest/fetch.py`. New ingestion code that hits
  EODHD directly bypasses the throttle and is a bug.
- **Do not let bulk loads fail silently.** Every per-ticker outcome —
  success or failure — writes a `load_runs` row. The `bulk_load_jobs`
  checkpoint table makes resume possible.

## Shell execution rules

- **Never run `python -c "..."` (or `uv run python -c "..."`) with inline
  Python that contains `#` comments.** The shell treats `#` as a comment
  delimiter inside double-quoted strings on some configurations, which
  silently truncates the script. Use a temporary `.py` file with
  `uv run python <file>`, or a heredoc:
  ```bash
  uv run python - <<'EOF'
  # comments are safe here
  print("hello")
  EOF
  ```

## Build / test commands

Confirmed interface (as of Phase 8); Docker variants added in Phase 9.

### Native (no Docker)

```bash
uv sync                                  # install deps
uv run pytest                            # run tests
uv run ruff check . && uv run black --check .   # lint + format check
uv run python scripts/load_daily.py      # fetch + ingest universe
uv run python scripts/rebuild.py         # full rebuild from raw (no fetch)
uv run python scripts/add_ticker.py AAPL # add a ticker and backfill
uv run python scripts/bulk_load.py --file tickers.txt   # Phase 9
uv run python scripts/bulk_load.py --resume <job_id>    # Phase 9
uv run streamlit run src/app/Home.py     # launch dashboard
```

### Docker (Phase 9 onward)

```bash
docker compose build                                    # build the image
docker compose run --rm app uv run pytest               # tests
docker compose run --rm app uv run python scripts/load_daily.py
docker compose run --rm app uv run python scripts/bulk_load.py --file tickers.txt
docker compose up streamlit                             # UI on :8501
docker compose run --rm app /bin/bash                   # shell into the container
```

Or via the Makefile shortcuts: `make load`, `make ui`, `make shell`,
`make test`.

## Working with the data: sample query patterns

### Point-in-time trailing P/E

The most-repeated pattern in this codebase is the point-in-time join between
prices, shares outstanding, and quarterly fundamentals. DuckDB's `ASOF JOIN`
makes it readable:

```sql
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
principle #2. The `universe` join scopes a screen to currently-followed
names.

### Display vs. comparison set: sector median P/E with a watchlist

When a watchlist is active, only those tickers are displayed, but the
sector median is computed over the full active universe:

```python
def sector_median_pe(con, display_filter: list[str] | None = None) -> pd.DataFrame:
    # comparison set: ALWAYS the full active universe
    medians = con.execute("""
        SELECT sm.gic_sector, MEDIAN(tm.trailing_pe) AS median_pe
        FROM trailing_multiples_daily tm
        JOIN security_master sm USING (ticker)
        WHERE tm.ticker IN (SELECT ticker FROM universe WHERE active)
          AND tm.date = (SELECT MAX(date) FROM prices_daily)
        GROUP BY sm.gic_sector
    """).df()

    # display set: medians stay, only constituent rows are filtered
    constituents = con.execute("""
        SELECT sm.gic_sector, tm.ticker, tm.trailing_pe
        FROM trailing_multiples_daily tm
        JOIN security_master sm USING (ticker)
        WHERE tm.ticker IN (SELECT ticker FROM universe WHERE active)
          AND tm.date = (SELECT MAX(date) FROM prices_daily)
    """).df()
    if display_filter is not None:
        constituents = constituents[constituents.ticker.isin(display_filter)]

    return medians, constituents
```

The two pieces are computed against different ticker sets *by design*.

## Phase 4 decisions (resolved open questions)

### Beta benchmark: SPY only

SPY is loaded into `prices_daily` like any other ticker. To get beta
computed in `technicals_daily`, run `add_ticker(con, "SPY")` once (or
include it in `config/universe.yml` seed if desired). Beta is NULL for all
dates where `prices_daily` has no SPY row. Per-region benchmarks are
deferred to a future phase.

### Net debt formula

`long_term_debt_total + short_term_debt - cash_and_short_term_investments`
(COALESCE to 0 for missing components). See `src/compute/multiples.py`.

### Derived views live in Python, not in migrations

TTM, multiples, and technicals views are created via `src/compute/ttm.py`,
`src/compute/multiples.py`, and `src/compute/technicals.py` using
`CREATE OR REPLACE VIEW`. `schema/runner.py::open_db()` calls
`compute.setup_views(con)` after migrations so every connection has the
views. No migration file is needed for views — they are code, not schema
state.

### `add_ticker` ordering fix

`add_ticker` writes a pending `active=false` universe row **before** ingest
begins so warehouse data is always traceable. On ingest failure for a
brand-new ticker the pending row is removed, keeping the universe clean.
Notes are updated when explicitly re-provided on re-add.

## Phase 5 decisions (resolved open questions)

### TTM timing unified to `earnings_events.report_date`

All four TTM views (`ttm_eps`, `ttm_revenue`, `ttm_ebitda`, `ttm_fcf`)
source `report_date` from `earnings_events` by joining on
`(ticker, fiscal_period_end)`. The initial implementation of `ttm_revenue`,
`ttm_ebitda`, and `ttm_fcf` used the statement table's own `filing_date`,
which diverged from `ttm_eps`. Unified to prevent cross-multiple timing
drift around earnings windows.

### Beta benchmark ticker from settings

`technicals_daily` reads `config/settings.yml → benchmark.ticker` at view
creation time. Default: `SPY.US`. Hardcoding `'SPY'` would silently produce
NULL beta because EODHD uses the `.US` suffix convention.

### `queries.py` layer: SQL and DataFrame computations

`src/app/queries.py` is the single place for all data access. This includes
both SQL queries and pure DataFrame computations that are better expressed
in Python (e.g. `valuation_stats`). Page files call only `queries.*` — no
SQL or pandas aggregation in pages.

### `matplotlib` required for `background_gradient`

Added `matplotlib` to `[dependencies]` in `pyproject.toml`. Omitting it
causes a hard `ImportError` at render time.

## Phase 6 decisions (resolved open questions)

### EODHD error responses validated at the fetch layer

`fetch_fundamentals()` and `fetch_prices()` validate the vendor response
before returning. Error-dict, missing `General.Code`, and non-array prices
responses raise `ValueError`. `fetch_and_ingest()` fails fast on the fetch
itself, which means `add_ticker()` cannot activate a ticker when EODHD
returns a plausible-looking but invalid payload.

### Warehouse path centralized in `src/schema/runner.py`

`runner.warehouse_path()` returns the absolute warehouse path from
`config/settings.yml`, with `WAREHOUSE_PATH` env var as an explicit
override. All CLI scripts call it instead of defaulting to a CWD-relative
string.

### Snapshot coverage on Universe management page

`queries.snapshot_coverage()` returns per-active-ticker first/last snapshot
date and total days collected. Forward-looking screens (Phase 13B) require
≥30 days of snapshot history per ticker.

### `next_period_end` replaces `next_earnings`

The Deep Dive header field is the end of the upcoming fiscal quarter, not
the actual report date.

### Streamlit width API

`use_container_width=True` is deprecated. Use `width="stretch"`.

## Phase 7 decisions (resolved open questions)

### SQL in `src/screens/trailing.py`, thin wrappers in `queries.py`

Screen functions live in `src/screens/trailing.py` and return full-universe
DataFrames. Optional filter parameters are keyword-only; unset parameters
leave the ticker in. `queries.py` exposes thin wrappers — no SQL in pages.

### Fetch-then-filter in Python for optional parameters

Each screen fetches the full active universe from DuckDB and applies
Python-side filters. The universe is small (~10–500 tickers); this avoids
the complexity of parameterized optional SQL conditions while keeping
queries readable.

### `PERCENT_RANK() OVER (PARTITION BY ticker ORDER BY ...)` for relative history

DuckDB's `PERCENT_RANK()` is a window function. Partitioning by ticker and
ordering by the multiple value produces each row's rank within that
ticker's own history. `min_history_days` parameter gates out tickers with
too little history (default 252 trading days).

### ROIC formula

`ROIC = TTM operating income / (total_stockholder_equity +
long_term_debt_total + short_term_debt)`. COALESCE debt to 0. Only
positive invested capital produces a meaningful ROIC; NULL otherwise.

### Margin expansion and FCF conversion

Margin expansion compares current quarter to 4 quarters prior (YoY) via
`ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fiscal_period_end DESC)`.
FCF conversion = TTM FCF / TTM net income × 100, NULL when TTM net income
≤ 0 to avoid negative conversion ratios from loss years.

## Phase 8 decisions (resolved open questions)

### Sector queries in `src/screens/sectors.py`

Grouped by `security_master.gic_sector` and sub-industry. Median trailing
multiples, growth, margins, and yield computed per group. Page imports via
`queries.py` — no raw SQL in page files.

### Bulk add via textarea and `.txt` file

`bulk_add_tickers(con, tickers)` in `src/universe.py` wraps `add_ticker`
per ticker and returns `list[tuple[ticker, ok, message]]`. Lines starting
with `#` and blank lines are ignored. Bare US tickers pass through
unchanged; the fetch layer appends `.US` automatically.

The bulk-add input parsing logic is the seed of `src/ticker_input.py`
extracted in Phase 9. Watchlist creation (Phase 10) reuses the same
function — see anti-pattern "Do not reimplement the ticker-input parser."

## Phase 9 decisions

### Shared ticker-input parser (`src/ticker_input.py`)

Pure function `parse_ticker_input(raw_text: str) -> list[str]`. Strips
whitespace-only lines, ignores `#`-prefixed lines, returns canonicalized
ticker strings (uppercased, exchange suffix preserved where given). Called
by both the Phase 8 bulk-add flow (refactored to use it) and the Phase 10
watchlist-from-file flow.

### Rate limiting in one place

`config/settings.yml` carries `eodhd.rate_limit.requests_per_minute` and
`eodhd.rate_limit.requests_per_day`. The throttle is applied inside
`src/ingest/fetch.py`. New EODHD-touching code MUST go through `fetch.py`
or its wrapper. Defaults conservative (e.g., 20 RPM) until the subscription
tier is confirmed; raise after the first successful bulk load.

### `bulk_load_jobs` checkpoint table

```sql
CREATE TABLE bulk_load_jobs (
    job_id INTEGER,
    ticker VARCHAR,
    status VARCHAR,           -- 'pending' / 'ok' / 'failed'
    error_message VARCHAR,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    PRIMARY KEY (job_id, ticker)
);
```

`scripts/bulk_load.py --file tickers.txt` creates a job, inserts pending
rows, processes them in batches with rate-limit pacing, updates status per
ticker. `--resume <job_id>` continues from the last pending row.

### `load_runs` table (universal monitoring)

```sql
CREATE TABLE load_runs (
    ticker VARCHAR,
    run_started_at TIMESTAMP,
    run_finished_at TIMESTAMP,
    status VARCHAR,           -- 'ok' / 'failed'
    duration_ms INTEGER,
    error_message VARCHAR,
    source VARCHAR,           -- 'daily' / 'bulk' / 'manual'
    PRIMARY KEY (ticker, run_started_at)
);
```

A decorator (`@with_load_run(source)`) on `fetch_and_ingest` writes a row
per attempt. Universe page reads from this for the "last load" and
"status" columns and the price-range columns are joined from
`prices_daily`.

### Docker layout

Single `Dockerfile`: `python:3.11-slim` base, installs `uv`, copies repo,
no entrypoint. `docker-compose.yml` defines:

- `app` — one-shot service for ingest scripts.
- `streamlit` — long-running UI on port 8501.

Both mount `./data:/app/data` and `./.env:/app/.env:ro`. A `Makefile`
provides `make load`, `make ui`, `make shell`, `make test`. No host-specific
paths in the image — same setup runs on EC2 later.

### DuckDB single-writer constraint

Phase 9 ships the simplest mitigation: schedule loads outside UI hours
(default 02:00 local via the sample crontab). Document the constraint in
this file. Read-only Streamlit mode is deferred unless option 1 proves
painful.

### Conservative configuration over premature optimization

The first 500-ticker load completes overnight at 20 RPM (≈25 minutes per
100 tickers). Raise the rate AFTER verifying the load worked cleanly. Do
not crank settings to "fast" before observing one successful run.

## Phase 10 decisions

### Snapshot semantics

Watchlists are frozen at creation. "Save current view as watchlist"
captures the ticker list as currently displayed; it does NOT capture the
filter parameters for later re-evaluation. Filter-parameter capture is
explicit future work.

### Schema reserves portfolio columns

`watchlist_membership.shares` and `cost_basis` are nullable from Phase 10.
No UI consumes them yet. A later sub-phase or Jira ticket adds:
- A "Portfolio mode" toggle on the watchlist edit form
- `shares` / `cost_basis` editable cells
- Calculated columns: position value, weight, gain/loss, sector allocation

### Active-watchlist state

Stored in `st.session_state["active_watchlist_id"]`. Sidebar selectbox in
`src/app/Home.py` (rendered on every page via Streamlit's multi-page
mechanism). Defaults to "Full universe" (no filter).

### Display set vs. comparison set, in code

Every `queries.py` function that touches a distribution-derived value
(median, percentile, sector aggregate) has signature:

```python
def some_screen(
    con,
    *,
    display_filter: list[str] | None = None,    # which rows the user sees
    comparison_set: list[str] | None = None,    # what statistics are computed against
    ...
) -> pd.DataFrame:
    ...
```

`comparison_set=None` means "full active universe." Pages pass
`display_filter = active_watchlist_members` and leave `comparison_set`
unset. Tests assert that the median, percentile, or sector aggregate is
unchanged when `display_filter` is set but `comparison_set` is not.

### Country-scoped comparisons: data ready, code not yet

`security_master.country` already exists. A future enhancement
parameterizes `comparison_set` construction with a scope (`"universe"` |
`"country"` | `"sector"`). Not built in Phase 10. The schema does not
need to change.

## Phase 11 decisions

### `period_type` discriminator on statement tables

Migration `002_statements_period_type.sql` adds:

```sql
ALTER TABLE income_statement ADD COLUMN period_type VARCHAR
    NOT NULL DEFAULT 'quarterly';
-- Drop and re-add primary key with period_type included
```

(Same for `balance_sheet`, `cash_flow`.) Backfill: existing rows default
to `'quarterly'`.

### Parser ingests both `.quarterly` and `.yearly`

`financials.py` iterates over both arrays with one mapping function,
emitting rows with `period_type='quarterly'` or `'annual'`. Same field-name
normalization (camelCase → snake_case) for both. Annual rows carry
`report_date` from the annual filing's `filing_date`, which differs from
the Q4 quarterly `report_date`.

### Backfill via re-ingest

After the migration ships, run `scripts/bulk_load.py --file
<active_universe>.txt` (or a dedicated re-ingest script) to populate
annual rows. Idempotency means existing quarterly rows are untouched.

### UI toggles default to current behavior

Deep Dive Statements panel: Period = Quarterly, Depth = Summary, Units =
Billions. Existing users see the same view they saw before Phase 11; new
options are opt-in.

### Units conversion in the page, not in SQL

The underlying query returns canonical raw values. A small helper
multiplies by 1e-9 / 1e-6 / 1e-3 / 1 for display and appends a suffix to
the column header. SQL stays simple and the data layer remains canonical.

## Phase 12 decisions

### `st.dialog` for the drill-down

Streamlit's modal dialog is the right primitive here. Triggered by a
button per universe row. Pop-up state is local to the page; closing the
dialog does not clear other UI state.

### Pagination, default 100

`queries.prices_page(ticker, page_size, offset, date_from=None,
date_to=None)` uses `LIMIT`/`OFFSET` on `prices_daily` ordered by date
desc. Existing `(ticker, date)` index makes this O(log n). Page-size
selector offers 50 / 100 / 250 / 500.

### Prices tab values in raw units

Prices are share-level numbers; conversion to Billions makes no sense.
The Phase 11 units toggle does not apply here.

### Read-only display, full stop

No edit affordances on either tab. Data correction goes through
re-ingestion, not through the UI.

## Phase 13 decisions

### Column-presence check is a prerequisite

Before building screens, verify `analyst_estimates_history` actually
persists the vendor's pre-computed trend and revision fields:

- `eps_trend_current`, `eps_trend_7days_ago`, `eps_trend_30days_ago`,
  `eps_trend_60days_ago`, `eps_trend_90days_ago`
- `eps_revisions_up_last_7days`, `eps_revisions_up_last_30days`,
  `eps_revisions_down_last_7days`, `eps_revisions_down_last_30days`
- Same set for revenue.

If any are missing, ship a schema migration adding them and re-ingest the
universe. The fields are zero-cost to store; this is one-time work.

### Screens grouped by data dependency, not by metric

The Forward Screens page has two clearly labeled sections:
"Vendor-provided trends (works immediately)" and "Snapshot history (≥30
days)." The grouping makes it obvious which screens will produce signal
on a new ticker and which need to accumulate history.

### Snapshot-history gating

Phase 13B screens take an explicit `min_history_days` parameter (default
30) and surface excluded tickers as a count ("3 tickers have insufficient
history") rather than dropping them silently. Filed under principle #2
indirectly: showing an empty result for a ticker without telling the user
why is confusing.

### Watchlist interaction

Both 13A and 13B respect the active watchlist for display but not for
comparison (per Phase 10 decision). "Save as watchlist" button on each
screen captures the displayed ticker list.

## When in doubt

- Prefer adding a test over adding a comment.
- Prefer a materialized view over a stored derived column.
- Prefer raising a question in PLAN.md "open questions" over making an
  undocumented decision.
- Prefer breaking up a phase if it gets too large; the phase boundaries in
  PLAN.md exist to keep deliverables shippable.
- Prefer shared utilities over copy-pasted logic. Two implementations of
  the "same" thing will drift apart silently.
- From Phase 9 onward, prefer testing against the loaded production
  universe (500+ tickers). Performance issues, edge cases, and
  sector-structure mismatches surface there that the 10-ticker fixture
  hides.
