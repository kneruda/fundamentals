# AGENTS.md

> Living design document for the fundamentals dashboard. Read this first.
> `REVIEW.md` is a snapshot code review; `PLAN.md` lists the open backlog.
> `CLAUDE.md` is a one-line pointer to this file — keep them in sync.

## Mission

Personal equity fundamentals dashboard tracking valuation, profitability,
growth, balance-sheet strength, and analyst expectations for a
user-managed universe. Four modes:

1. **Universe management** — add/remove tickers via UI or CLI; new tickers
   backfill all available history immediately. Bulk loads of hundreds of
   tickers run from a single command.
2. **Drill-down** on a single ticker: full statements (quarterly + annual,
   summary or full, configurable units), historical multiples, analyst
   expectations.
3. **Screens** — trailing fundamentals, relative-to-own-history valuation,
   vendor-provided forward estimate trends, and rating-change signals
   from our accumulated daily snapshots.
4. **Watchlists / portfolios** — named subsets of the universe (manual,
   file upload, or save-from-screen) that scope the *display* of every
   screen while leaving the *comparison universe* (medians, percentiles,
   sector aggregates) anchored to the full active universe.

## Scope

### In scope
- Universe table (user-editable through UI/CLI; YAML seed only at setup)
- Static company data (identifiers, sector classification, fiscal year
  end, currency, country)
- Quarterly **and** annual fundamentals (TTM/MRQ aggregates from
  `Highlights`; full statements from `Financials.*.quarterly` and
  `Financials.*.yearly`)
- Full statements: income / balance sheet / cash flow
- Earnings events (estimates, actuals, surprises, report dates)
- Dividend events and annual history
- Analyst expectations (consensus rating, target price, forward EPS per
  future period, vendor 7/30/60/90-day trend deltas + revision counts)
- Daily price history (separate EODHD endpoint, same vendor)
- FX rates (USD reporting currency; schema supports non-USD tickers but
  loader not activated until needed)
- Watchlists with optional `shares` / `cost_basis` columns (schema ready;
  portfolio calculations are future work)

### Explicitly NOT tracked
Fields present in the vendor JSON but deliberately omitted. If a future
ticket needs any of these, raise it for discussion before implementing:

- `Holders.*`, `InsiderTransactions.*`, `General.Officers`
- `Technicals.*` (we derive our own)
- `SharesStats.SharesShort*`, short-interest fields
- `ESGScores.*` (vendor disclaims production-readiness)
- `General.AddressData.*` beyond country and currency
- `General.Listings.*` cross-listings (record primary exchange only)

## Core design principles

1. **Cadence-aware storage.** Static, quarterly, event-driven, and daily
   data live in different tables. Joins compose them; we never collapse
   to one wide row per ticker per day.
2. **Point-in-time integrity.** Every historical computation reflects
   what was knowable on that date. Quarterly fundamentals are knowable
   as of `report_date` (sourced from vendor `filing_date`), **not**
   fiscal period end. Analyst data is knowable only on dates snapshotted.
3. **Derive, don't store.** Market cap, trailing multiples, MAs, beta,
   52-week ranges, portfolio values — computed on demand or as views.
   Never persisted as authoritative.
4. **Snapshot only forward-looking data.** Analyst ratings, target
   prices, forward EPS estimates per future period — and only these —
   are captured in append-only daily snapshots.
5. **FX-aware from day 1.** Every monetary column has a currency code.
6. **Display set ≠ comparison set.** Watchlists filter the rows the user
   *sees*; medians/percentiles/sector aggregates always run over the
   full active universe. A 3-stock watchlist does not redefine "median
   sector P/E."
7. **Shared utilities.** One ticker-input parser, one TTM definition, one
   trailing-multiples view. Duplication silently drifts.

## Vendor

**EODHD** (eodhd.com). API key in `.env` as `EODHD_API_TOKEN`. Two
endpoints:

- `/api/fundamentals/<ticker>` — the big JSON.
- `/api/eod/<ticker>?period=d` — flat daily OHLCV array.

EODHD quirks honored in the parser:

- Many numeric fields are JSON strings (`"0.0944"`); parse to float.
- Vendor field names are camelCase; we normalize to snake_case in
  `src/ingest/sections/_util.py`. Two typo fixes are baked in:
  `capitalSurpluse → capital_surplus`, `nonCurrrentAssetsOther →
  non_current_assets_other`, plus `goodWill → goodwill`.
- `Financials.*.{quarterly,yearly}` use `date` for fiscal period end and
  `filing_date` for report date. `Earnings.History` uses `reportDate`.
  Both land in our `report_date` column.
- A 200 OK can carry `{"Error": "Ticker Not Found."}`. `fetch.py`
  validates response shape before returning.

## Ingestion model

The vendor returns two files per ticker: a fundamentals JSON (~100 KB–
1.5 MB) and a prices JSON (~1.5 MB for a 45-year history). **We
re-download both in full every day.** Bandwidth is cheap; partial sync
is expensive engineering with no upside.

### Per-section semantics

| Source section / field | Target table | Write mode |
|---|---|---|
| `General.*` | `security_master` | UPSERT by `ticker` |
| `Highlights.*` | `quarterly_fundamentals` | UPSERT by `(ticker, mrq_period_end)` |
| `Financials.{IS,BS,CF}.{quarterly,yearly}` | `income_statement` / `balance_sheet` / `cash_flow` | UPSERT by `(ticker, fiscal_period_end, period_type)` |
| `Earnings.History` | `earnings_events` | UPSERT by `(ticker, fiscal_period_end)` |
| `outstandingShares.quarterly` | `shares_outstanding` | UPSERT by `(ticker, period_end)` |
| `SplitsDividends.NumberDividendsByYear` | `dividends_annual` | UPSERT by `(ticker, year)` |
| `SplitsDividends.{ExDividendDate, …}` | `dividends_declared` | UPSERT by `(ticker, ex_date)` |
| `SplitsDividends.LastSplit*` | `splits` | UPSERT by `(ticker, split_date)` |
| `AnalystRatings.*` + `Highlights.EPSEstimate*` | `daily_forward_snapshot` | UPSERT by `(ticker, snapshot_date)` (one row per day) |
| `Earnings.Trend.*` (incl. trend deltas + revision counts) | `analyst_estimates_history` | UPSERT by `(ticker, snapshot_date, period_end)` |
| Price file rows | `prices_daily` | UPSERT by `(ticker, date)`; `adjusted_close` overwritten across the whole history |
| Each ingest attempt | `load_runs` | APPEND |

### Idempotency requirement

Re-running ingestion on the same input files MUST leave the warehouse
byte-identical (modulo `loaded_at`). This is what makes "re-download
everything every day" safe. Every UPSERT is keyed on a natural key; every
APPEND is deduped by `(natural_key, snapshot_date)`.

### Adjusted close

The vendor's `adjusted_close` is back-adjusted for **all subsequent**
splits and dividends — it's retroactively mutable. On every price load we
overwrite the whole `adjusted_close` column for that ticker. Raw OHLC
stays put. True point-in-time prices (e.g., for backtesting) would
require a corporate-actions table; not built yet.

### Per-section ingestion modules

One module per logical section in `src/ingest/sections/`. A failure in
one section is caught in `orchestrator.ingest_ticker` and logged; the
other sections still load. `fetch_and_ingest` writes a `load_runs` row on
success or failure.

### Bulk loads

`scripts/bulk_load.py --file tickers.txt` (or `--resume <job_id>`) drives
the rate-limited, checkpointed bulk loader in `src/ingest/bulk.py`. The
`bulk_load_jobs` table tracks per-ticker status (`pending` / `ok` /
`failed`); resume reads pending rows and continues.

## Universe management

Source of truth: the `universe` table. `config/universe.yml` is read
**only** at setup time by `scripts/seed_universe.py`.

`add_ticker(con, ticker, notes=None)` in `src/universe.py`:

1. Writes a pending `active=false` row.
2. Calls `fetch_and_ingest`. On failure, deletes the pending row.
3. On success, flips `active=true`.

`remove_ticker` is a soft delete (`active=false`); history is preserved.

Both the CLI (`scripts/add_ticker.py`) and the Universe page call
`add_ticker()`. Bulk add (`bulk_add_tickers`) wraps it with per-ticker
error capture.

## Watchlists

Watchlists are named, **snapshot** subsets — frozen at save time. A
watchlist created from a screen result does not auto-update; re-save to
refresh.

`watchlist_membership.shares` and `cost_basis` are nullable from day one
(schema reserved for portfolio mode). No UI consumes them yet.

Active watchlist lives in `st.session_state["active_watchlist_id"]`,
selectable from the sidebar on every page. Default: "Full universe."

Watchlist creation uses the same `parse_ticker_input` parser as bulk
universe upload. Manual entry, file upload, and "save current screen"
all funnel through the same code path.

## Tech stack

- **Python 3.11+**, **uv** for dependencies, **ruff** + **black** for
  lint/format
- **DuckDB** for storage — single-file analytical database. One writer at
  a time (see "DuckDB single-writer constraint" below)
- **pandas** for per-ticker parsing; **polars** available for heavier
  query-side joins
- **Streamlit** for the UI. `st.dialog` for the Phase 12 drill-down modal
- **httpx** (sync) for HTTP, with retry/backoff + a single shared rate
  limiter
- **Docker** + **docker-compose**: one image, two services (`app` for
  one-shots, `streamlit` for the long-running UI)
- **pytest** for tests. Date lagging, point-in-time joins, restatement
  handling, display-vs-comparison-set splits all have explicit tests
- **Configuration**: `.env` for secrets (`EODHD_API_TOKEN`),
  `config/settings.yml` for paths, throttles, benchmark ticker, archive
  retention

## Repository layout

```
.
├── AGENTS.md             # this file
├── PLAN.md               # backlog (Jira-driven from now on)
├── REVIEW.md             # snapshot code review
├── README.md             # quick start
├── Dockerfile
├── docker-compose.yml
├── Makefile              # make load, make ui, make shell, make test
├── pyproject.toml        # uv-managed; deps listed here
├── .env.example          # documents EODHD_API_TOKEN
├── config/
│   ├── universe.yml      # SEED list; not source of truth at runtime
│   └── settings.yml      # paths, FX base, throttles, benchmark
├── data/
│   ├── raw/{fundamentals,prices}/   # <ticker>.json, replaced daily
│   ├── archive/          # optional dated copies for audit
│   ├── logs/             # cron + bulk-load logs
│   └── warehouse.duckdb  # the database
├── src/
│   ├── universe.py       # add/remove/list + bulk_add_tickers + parse_tickers
│   ├── watchlist.py      # create/delete/rename/list/get_membership
│   ├── ticker_input.py   # parse_ticker_input — shared parser
│   ├── ingest/
│   │   ├── sections/     # one module per JSON section
│   │   ├── fetch.py      # EODHD client (rate limit + retry)
│   │   ├── bulk.py       # bulk_load_jobs-backed checkpointed loader
│   │   └── orchestrator.py
│   ├── schema/
│   │   ├── runner.py     # open_db + migration runner + warehouse_path
│   │   └── migrations/   # 001_initial.sql, 002_monitoring.sql, …
│   ├── compute/          # ttm, multiples views; recompute_technicals() for the technicals table
│   ├── screens/          # trailing, sectors, forward_vendor, forward_history, technicals
│   └── app/              # Home.py + pages/ + queries.py + sidebar.py
├── tests/
│   ├── fixtures/         # AAPL-Fundamentals.json + AAPL.json
│   └── test_phase*.py
└── scripts/
    ├── load_daily.py     # cron entry point
    ├── seed_universe.py
    ├── add_ticker.py
    ├── bulk_load.py
    └── cron.example
```

## Data model summary

| Table | Grain | Cadence | Notes |
|---|---|---|---|
| `universe` | one row / followed ticker | user | `ticker`, `added_at`, `active`, `notes` |
| `security_master` | one row / ticker | static | identifiers, sector, currency, country, `is_delisted` |
| `quarterly_fundamentals` | ticker × MRQ end | quarterly | TTM aggregates from `Highlights` |
| `income_statement` / `balance_sheet` / `cash_flow` | ticker × period × `period_type` | quarterly + annual | full statements (34 / 64 / 32 columns) |
| `earnings_events` | ticker × fiscal quarter | event | report date, EPS estimate/actual, surprise |
| `shares_outstanding` | ticker × as-of date | quarterly | |
| `dividends_declared` | ticker × ex-date | event | rate, ex, pay date |
| `dividends_annual` | ticker × year | annual | count of dividends |
| `splits` | ticker × split date | event | factor string |
| `daily_forward_snapshot` | ticker × snapshot date | daily | analyst ratings + target + forward EPS |
| `analyst_estimates_history` | ticker × snapshot × future period | daily | per-period detail + 7/30/60/90-day deltas + revision counts |
| `prices_daily` | ticker × trading date | daily | OHLCV native ccy; `adjusted_close` re-derived each load |
| `fx_rates_daily` | currency × date | daily | rate to USD (not loaded yet) |
| `watchlist` / `watchlist_membership` | user | user | snapshot ticker lists |
| `load_runs` | per (ticker, run_started_at) | event | PK `(ticker, run_started_at)`, plus `status`, `duration_ms`, `error_message` |
| `bulk_load_jobs` | one row / job × ticker | event | `(job_id, ticker)` PK, `created_at`/`updated_at` |
| `technicals_daily` | ticker × trading date | daily | table, recomputed from `prices_daily` via `recompute_technicals()` |

Derived (views, never persisted as authoritative):
- `ttm_eps`, `ttm_revenue`, `ttm_ebitda`, `ttm_fcf` — 4-quarter rolling
  sums, all timed off `earnings_events.report_date`
- `trailing_multiples_daily` — `ASOF LEFT JOIN` of price × shares × TTM ×
  balance sheet

`technicals_daily` is the documented exception to the "derive, don't store"
principle. It is a persistent table (migration `007`), not a view, because
several indicators (Wilder's RSI, MACD, ATR, EMAs) require recursive/EWM
computation that is awkward in pure SQL. The table is fully regenerable from
`prices_daily` via a single deterministic function (`recompute_technicals`)
and is never written by anything else, so it cannot silently disagree with
its inputs in the way stored derived columns typically can.

Views are created by `src/compute/setup_views(con)`, called from
`schema/runner.open_db` after migrations. Not migration files; they're
code. `technicals_daily` is created by migration `007_technicals_daily_table.sql`
and populated by `src/compute/technicals.recompute_technicals()`.

## Conventions

- **Primary identifier**: `ticker` (e.g. `AAPL`, `7203.TSE`). Vendor
  format. Original `Code` and `Exchange` stored separately in
  `security_master`.
- **Dates**: ISO 8601 in storage. Timestamps in UTC.
- **Currency**: every monetary column has a sibling `currency` column. No
  silent USD assumption. `ingest_highlights` and `ingest_financials` raise
  `ValueError` if `General.CurrencyCode` is missing rather than defaulting
  to USD; the orchestrator logs the failure into `load_runs` and the rest
  of the ticker still loads.
- **Nulls**: SQL `NULL`. No sentinel values.
- **`loaded_at`** on every UPSERT table. Latest write wins.
- **Monetary precision**: `DOUBLE`. Sufficient for this project.
- **Field naming**: camelCase from vendor → snake_case in DuckDB.
  Mapping lives only in `src/ingest/sections/_util.py:col`.
- **`period_type`**: lowercase `'quarterly'` / `'annual'`. Every query
  against a statement table MUST filter on it. Helpers in `queries.py`
  always do.
- **Display set vs. comparison set**: any `queries.*` function that
  produces a distribution-derived value takes an explicit `display_filter`
  and (where relevant) `comparison_set`. Tests pin the invariant.
- **Pagination**: `queries.prices_page(...)` with `LIMIT`/`OFFSET`.
  Default page size 100.
- **Watchlist names**: case-insensitive uniqueness; stored as entered,
  compared lowered. Enforced by a unique index on `lower(name)`.
- **Schema changes**: append-only migration files in
  `src/schema/migrations/` with a leading numeric prefix. Never edit a
  past migration. View definitions live in `src/compute/`, not in
  migrations.
- **Statement-shape migrations**: DuckDB doesn't support
  `ALTER TABLE DROP/ADD PRIMARY KEY` — use rename/recreate/copy. See
  `004_statements_period_type.sql` for the canonical pattern.

## Anti-patterns and pitfalls

- **Don't trust EODHD 200 responses blindly.** `fetch_fundamentals` /
  `fetch_prices` validate shape and raise `ValueError`. Don't bypass.
- **Don't use CWD-relative warehouse paths in scripts.** Use
  `schema.runner.warehouse_path()`.
- **Don't use `use_container_width=True` in Streamlit.** Use
  `width="stretch"` or `width="content"`.
- **Don't store vendor-computed multiples** for historical purposes
  (`Valuation.TrailingPE`, `Highlights.MarketCapitalization`, …). Compute
  them.
- **Don't lag fundamentals by `fiscal_period_end`.** Use `report_date`.
- **Don't try to incrementally fetch prices.** Pull the full series; let
  UPSERT do the work.
- **Don't use raw `close` for split-spanning return math.** Use
  `adjusted_close`.
- **Don't overwrite historical snapshot rows** when the vendor revises a
  number. APPEND; treat the highest `loaded_at` as current.
- **Don't silently drop delisted tickers.** Set `is_delisted=true`,
  preserve history, use `universe.active` to control current screens.
- **Don't let one failing ticker break the daily load.** Per-section
  errors are caught; the rest of the ticker still loads.
- **Don't call vendor APIs from the UI layer.** The UI reads only from
  DuckDB. ETL is a separate process. Exception: `add_ticker()`.
- **Don't store anything derived from forecasts as fundamental.** Forward
  P/E, PEG, target-implied return — snapshot-time observations only.
- **Don't commit `.env`.** Use `.env.example` for documentation.
- **Don't use `is` as a SQL table alias in DuckDB.** Reserved.
- **Don't use `PERCENT_RANK() WITHIN GROUP (...)` in DuckDB.**
  PostgreSQL-only. Plain `PERCENT_RANK() OVER (...)` works and is what
  the screens use.
- **Don't use `pd.DataFrame.applymap()`.** Removed in pandas 2.1; use
  `.map()`.
- **Don't forget `load_dotenv()` in Streamlit pages that trigger EODHD
  calls.**
- **Don't apply watchlist filters to median/percentile/sector aggregate
  calculations.** Display set ≠ comparison set.
- **Don't reimplement the ticker-input parser.** Both bulk upload and
  watchlist creation call `parse_ticker_input`. Single point of truth.
- **Don't run `load_daily.py` and Streamlit against the warehouse
  simultaneously.** DuckDB single-writer. Default cron schedule (02:00
  local) avoids this.
- **Don't query statement tables without `period_type`.** Same
  `(ticker, fiscal_period_end)` can have a quarterly Q4 row AND an
  annual row. `queries.py` always filters.
- **Don't load full price history into one DataFrame for display.** A
  45-year series is 11,000+ rows. Use `queries.prices_page(...)`.
- **Don't store calculated portfolio values.** Derived from
  `watchlist_membership.shares × adjusted_close`.
- **Don't bake the EODHD throttle into call sites.** Goes through
  `fetch._get`.
- **Don't let bulk loads fail silently.** Every per-ticker outcome writes
  a `load_runs` row; checkpoints are in `bulk_load_jobs`.
- **Don't use `ewm(adjust=True)` for EMAs or Wilder's smoothing** in
  `recompute_technicals`. `adjust=False` (recursive first-value seed) matches
  TradingView, Bloomberg, and most charting platforms. `adjust=True` produces
  different values during the warm-up window.
- **Don't use `avg_loss.replace(0, NaN)` in RSI computation.** When all
  moves are gains (avg_loss = 0), the correct RSI is 100. Replacing 0 with
  NaN silently produces NaN instead of 100. Let pandas handle `gain / 0 = inf`
  naturally; `100 - 100 / (1 + inf) = 100`.
- **Don't query `technicals_daily` expecting it to auto-update.** Unlike
  views, the table does not reflect new `prices_daily` rows until
  `recompute_technicals()` is called. `fetch_and_ingest` calls it per-ticker;
  `rebuild.py` calls it for the full universe after the ingest loop.
- **Don't use f-string interpolation for cross-detection SQL window sizes**
  when values come from user input. The `lookback_days` used in the technicals
  screens is a typed Python int, not a string — f-string interpolation is safe
  there. Parameterize only string-typed user data.

## Shell execution rules

- **Never run `python -c "..."` with inline Python that contains `#`
  comments.** Some shell configurations treat `#` as a comment delimiter
  even inside double quotes, silently truncating the script. Use a
  temporary `.py` file or a heredoc:

```bash
uv run python - <<'EOF'
print("hello")
EOF
```

## Build / test commands

### Native

```bash
uv sync
uv run pytest
uv run ruff check . && uv run black --check .
uv run python scripts/load_daily.py
uv run python scripts/add_ticker.py AAPL
uv run python scripts/bulk_load.py --file tickers.txt
uv run python scripts/bulk_load.py --resume <job_id>
uv run streamlit run src/app/Home.py
```

### Docker

```bash
docker compose build
docker compose run --rm app uv run pytest
docker compose run --rm app uv run python scripts/load_daily.py
docker compose up streamlit                # UI on :8501
docker compose run --rm app /bin/bash
```

Or the Makefile: `make load`, `make ui`, `make shell`, `make test`.

## Reference query pattern: point-in-time trailing P/E

The most-repeated pattern. `ASOF JOIN` keeps it readable. The `>=` on
`report_date` (not `fiscal_period_end`) is the entire point of principle
#2:

```sql
SELECT p.ticker, p.date, p.adjusted_close, ttm.ttm_eps,
       p.adjusted_close / NULLIF(ttm.ttm_eps, 0) AS trailing_pe
FROM prices_daily p
ASOF LEFT JOIN ttm_eps ttm
  ON p.ticker = ttm.ticker AND p.date >= ttm.report_date
WHERE p.ticker IN (SELECT ticker FROM universe WHERE active);
```

## Known limitations

- **Debt classification ambiguity** between `short_term_debt`,
  `short_long_term_debt`, and `short_long_term_debt_total`. We use
  `long_term_debt_total + short_term_debt - cash_and_short_term_investments`
  for net debt and accept some noise.
- **Sector-structure mismatches** for banks, insurers, REITs: many
  statement fields are NULL or have different meanings. No
  sector-templated UI yet.
- **Restatement detection** is best-effort: latest write wins, no
  versioned history.
- **Multiple share classes** are treated as separate tickers (BRK.A vs
  BRK.B). Combining them is future work.
- **Pre-IPO short history** affects PERCENT_RANK over own history; the
  `min_history_days` parameter gates this on the relative-history
  screen.
- **Spin-offs** appear as new tickers; the parent's history doesn't carry
  over (acceptable for this project).
- **`adjusted_close` is retroactively mutable** by design — no
  point-in-time price view yet.
- **DuckDB single-writer constraint**: cron load and live Streamlit
  cannot share write access. The default 02:00 schedule avoids this.
- **Watchlists are snapshots**, not dynamic. Re-save to refresh.
- **Country-scoped comparisons not implemented.** Schema supports
  `security_master.country`; the change is in `queries.py` only.
- **Forward EPS estimates from `Highlights`** become stale relative to
  `Earnings.Trend` between earnings events — both are stored; UI uses
  Trend for screens, Highlights for the snapshot table.
- **Newly-added tickers** populate the growth-acceleration screen
  gradually: `quarterly_fundamentals` UPSERTs on MRQ, so historical
  growth values accumulate one quarter per ingest. Vendor-trend screens
  (Phase 13A) work immediately; rating-shift screens (Phase 13B) need
  ~30 days of snapshot history.
- **`next_period_end` relies on EODHD pre-populating** the next-quarter
  row in `Earnings.History` (with `eps_actual` NULL). If the vendor stops
  doing this, the Deep Dive header silently shows "—".

## When in doubt

- Prefer a test over a comment.
- Prefer a materialized view over a stored derived column.
- Prefer raising a question in `PLAN.md` over an undocumented decision.
- Prefer shared utilities over copy-paste.
- Prefer testing against the loaded universe (500+ tickers) — many edge
  cases (sector-structure mismatches, short history, very old data)
  surface there that the 10-ticker fixture hides.
