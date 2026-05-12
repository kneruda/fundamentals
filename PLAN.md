# PLAN.md

Phased implementation plan. Each phase has a clear deliverable, is
independently testable, and leaves the project in a runnable state. Do not
skip phases — later phases assume the earlier ones have stuck their landing.

Read `AGENTS.md` first; the design principles, vendor specifics, and
ingestion model there are the "why" behind every phase here.

## MVP definition

The MVP is "useful for one person making better decisions about a small,
self-curated universe":

- A user-editable universe (table-backed, ~10 tickers initially)
- DuckDB warehouse populated end-to-end from EODHD's fundamentals JSON and
  price JSON, including the `Financials` block
- A Streamlit app with three pages: **Universe table**, **Single-ticker deep
  dive**, and **Universe management** (add/remove/refresh tickers)
- Trailing-multiple screens working out of the box
- Daily forward-snapshot collection running

**Initial MVP universe** (decided): AAPL, MSFT, META, DIS, CRWD, NFLX, GOOG,
RBLX, U, PANW. Stored in `config/universe.yml` as a seed; the runtime source
of truth is the `universe` table.

**Out of MVP**: forward-looking screens (need ≥30 days of accumulated
snapshots), sector aggregates, calendar/events page, full FX activation
(designed-in but not loaded until Phase 8).

---

## Phase 0 — Project setup

**Deliverable**: empty project that installs, lints, tests, and runs end-to-end.

- Initialize repo with the layout in AGENTS.md.
- Set up `pyproject.toml` with Python 3.11+; pin DuckDB, pandas, polars,
  Streamlit, httpx, python-dotenv, PyYAML, pytest, ruff, black.
- Create `.env.example` documenting `EODHD_API_TOKEN`. Add `.env` to
  `.gitignore`.
- Create `config/universe.yml` with the 10 seed tickers above.
- Create `config/settings.yml` with data paths, `reporting_currency: USD`,
  and `archive_raw_files: true`.
- Write a `README.md` quickstart pointing at the commands in AGENTS.md.
- One smoke test (`tests/test_smoke.py`) that imports the top-level package.

**Done when**: `uv sync && uv run pytest` passes; `uv run ruff check .` is
clean; `git log` has a single setup commit.

---

## Phase 1 — Schema and section parsers

**Deliverable**: DuckDB warehouse populated for the seed universe from local
fixture files (no live vendor fetch yet).

The hard work of this phase is the **parser/writer per JSON section**, since
that's the central piece per the ingestion model in AGENTS.md.

- Write DDL for all tables in AGENTS.md's data model, including the
  `universe` table. Every monetary column has a currency. Every UPSERT table
  has `loaded_at` (used for recency/change detection, not row-version
  history). Use `DOUBLE` throughout — 15 significant digits is
  sufficient for all monetary and per-share figures in this project.
- One migration script (`src/schema/migrations/001_initial.sql`) creates
  everything. Migrations are append-only thereafter.
- Build a small migration runner that reads the `_schema_migrations` table
  and applies any new scripts in order. Idempotent (re-running does nothing
  if all migrations are present).
- Implement one module per section in `src/ingest/sections/`:
  - `general.py` — maps `General.*` → `security_master`
  - `financials.py` — maps `Financials.{Balance_Sheet, Income_Statement,
    Cash_Flow}.quarterly` → respective tables; uses `filing_date` as
    `report_date`; normalizes camelCase → snake_case (note two vendor
    typos: `capitalSurpluse` → `capital_surplus`, `nonCurrrentAssetsOther`
    → `non_current_assets_other`)
  - `earnings.py` — maps `Earnings.History` → `earnings_events`
  - `shares.py` — maps `outstandingShares.quarterly` → `shares_outstanding`
  - `dividends.py` — maps `SplitsDividends.*` to `dividends_declared`,
    `dividends_annual`, `splits`
  - `analyst_snapshot.py` — maps `AnalystRatings.*` +
    `Highlights.EPSEstimate*` → `daily_forward_snapshot`, and
    `Earnings.Trend` → `analyst_estimates_history`
  - `prices.py` — placeholder; full price ingestion lands in Phase 2
- `src/ingest/orchestrator.py`: `ingest_ticker(con, fundamentals_path)` that
  opens the file and dispatches to each section, catching per-section
  errors and logging them.
- Drop the AAPL fixture files into `tests/fixtures/` and run ingest against
  them.
- Tests:
  - End-to-end parse of `AAPL-WithFinancials.json` producing populated rows
    in every target table.
  - Targeted unit tests for tricky fields: null EPS actuals, string-encoded
    decimals in `Earnings.Trend` (e.g., `"0.0944"`), fiscal-quarter labels
    (`"2025-Q4"`), missing optional fields, BS fields that come back null
    for non-applicable line items (e.g., `intangibleAssets` on financials
    companies).
  - Idempotency: running `ingest_ticker` twice on the same file leaves the
    warehouse identical except for `loaded_at`.
  - Restatement: changing one BS number in the fixture and re-running causes
    the latest row to win via in-place update on the same natural key
    (row count unchanged).

**Done when**: AAPL fixture loads cleanly into every applicable table; SQL
spot-check on AAPL fundamentals matches the JSON source; re-running the
loader leaves row counts unchanged.

---

## Phase 2 — Vendor client + price ingestion

**Deliverable**: live ingestion from EODHD for an arbitrary ticker, including
price history with correct `adjusted_close` handling.

- `src/ingest/fetch.py`: EODHD API client. Reads `EODHD_API_TOKEN` from env.
  Rate-limited (respect EODHD's per-minute caps; see vendor docs for current
  limits), retries with backoff, returns raw JSON. Two functions:
  `fetch_fundamentals(ticker)` and `fetch_prices(ticker)`.
- `prices.py` section module (full implementation):
  - UPSERT raw OHLCV by `(ticker, date)`.
  - **REPLACE** the `adjusted_close` column for the entire ticker's history
    on each load — implemented as a single transaction. The cleanest pattern
    is a temp staging table + `UPDATE ... FROM staging` keyed on date.
- `src/ingest/orchestrator.py`: extend `ingest_ticker(ticker)` so it fetches
  both files (or reads from disk if already fetched today), optionally
  archives them to `data/archive/<date>/`, and dispatches to all section
  modules including `prices.py`.
- `scripts/load_daily.py`: skeleton orchestrator that iterates over the
  active universe and calls `ingest_ticker` for each. Per-ticker failures
  logged, not fatal.
- Tests:
  - Vendor client tested against recorded HTTP responses (vcr.py or similar)
    so tests don't hit the live API.
  - Adjusted-close replacement: starting with a warehouse holding obsolete
    `adjusted_close` values, running the loader leaves the column equal to
    the source file values for every date.
  - Idempotency on prices: re-running the loader does not change row counts.

**Done when**: running `ingest_ticker("AAPL")` against the live EODHD API
fully populates AAPL's data including 45 years of price history with correct
adjusted closes.

---

## Phase 3 — Universe management (CLI)

**Deliverable**: a working `add_ticker(ticker)` flow exposed as a CLI; the
universe table is the runtime source of truth.

- `src/universe.py`:
  - `add_ticker(ticker, notes=None)` — validates via a cheap EODHD call,
    inserts a row into `universe`, then calls `ingest_ticker(ticker)` to
    backfill all historical data. Idempotent: re-adding a ticker that
    already exists in `universe` re-runs the ingest but doesn't duplicate.
  - `remove_ticker(ticker)` — soft delete: sets `active = false`. Does not
    drop warehouse data.
  - `list_universe(active_only=True)` — returns DataFrame.
- `scripts/seed_universe.py` — reads `config/universe.yml` and calls
  `add_ticker` for each entry not already in the table. Designed to be run
  once at setup.
- `scripts/add_ticker.py` — `python scripts/add_ticker.py SHOP` style CLI.
- `scripts/load_daily.py` (extended): now reads the active universe from the
  table, not from YAML.
- Tests:
  - `add_ticker` for an invalid ticker (`add_ticker("FAKE")`) raises a clear
    error and leaves the warehouse untouched.
  - `add_ticker` for a valid ticker leaves the warehouse fully populated.
  - `remove_ticker` then `add_ticker` round-trips: the ticker is `active =
    true` again, history preserved.
  - Seed script is idempotent.

**Done when**: `uv run python scripts/seed_universe.py` populates the 10 MVP
tickers with full historical data; `uv run python scripts/add_ticker.py
SHOP` adds an 11th ticker and backfills it in a single command.

---

## Phase 4 — Computed multiples and technicals ✓ DONE

**Deliverable**: every (ticker, date) has correct trailing multiples and
technicals computable.

- TTM aggregation views (`src/compute/ttm.py` creating `ttm_eps`,
  `ttm_revenue`, `ttm_ebitda`) using `report_date` as the becomes-known
  timestamp from `earnings_events`.
- `trailing_multiples_daily` materialized view: P/E (price ÷ TTM EPS), P/S
  (mkt cap ÷ TTM revenue), P/B (price ÷ book value per share from
  `balance_sheet`), EV/EBITDA (EV computed from mkt cap + net debt), FCF
  yield (`freeCashFlow` from cash flow ÷ mkt cap).
- Mkt cap uses `adjusted_close × current_shares_outstanding` for consistency
  with adjusted EPS. (See AGENTS.md sample query pattern.)
- `technicals_daily` view: 20/50/200-day MA, 52-week high/low, realized
  volatility (rolling 60-day stdev × √252), beta vs. SPY (rolling 252-day
  regression). SPY price history is loaded via a "benchmark" entry in the
  universe or a separate `benchmarks_daily` table — decide in this phase.
- Point-in-time integrity tests (these are the most important tests in the
  whole project):
  - Trailing P/E on the day **before** an earnings report uses the **prior**
    quarter's TTM EPS.
  - Trailing P/E on the report date itself uses the **new** TTM EPS.
  - Negative-EPS tickers (RBLX, U) produce NULL P/E, not a divide-by-zero
    or a misleading negative multiple — this is a real test case from the
    MVP universe.
  - A multiple computed across AAPL's 2020-08-31 split shows no
    discontinuity (price and EPS both split-adjusted).

**Done when**: AAPL trailing P/E over 5 years matches public sources within
~1%; RBLX shows NULL P/E for all dates it had GAAP losses.

**Implementation notes (from Phase 4 review)**:
- TTM revenue, EBITDA, and FCF views were initially using the statement
  table's own `report_date`; corrected to join `earnings_events` on
  `(ticker, fiscal_period_end)` so all TTM views share one timing source.
- Beta benchmark hardcoded to `'SPY'` was corrected to read
  `benchmark.ticker` from `config/settings.yml` (value: `SPY.US`).

---

## Phase 5 — MVP UI ✓ DONE

**Deliverable**: a working Streamlit dashboard with three pages.

- `src/app/Home.py`: the **universe table**. Sortable and filterable. Pulls
  from `universe` (active only by default). Columns: ticker, name, sector,
  market cap, price, 1D %, trailing P/E, forward P/E, P/S, P/B, EV/EBITDA,
  dividend yield, EPS YoY, revenue YoY, consensus rating, target upside %.
  Conditional formatting (heatmap) on multiples and yield.
- `src/app/pages/1_Deep_Dive.py`: ticker selector + panels:
  - **Header**: name, ticker, sector, price, day change, market cap, next
    earnings date.
  - **Valuation history**: trailing P/E, P/S, P/B, EV/EBITDA over 1/3/5y
    with current vs. own median and percentile.
  - **Profitability & growth**: quarterly bars of revenue, margins, ROE,
    with YoY growth labels.
  - **Analyst view**: rating distribution, consensus dial, target with
    upside %.
  - **Earnings reaction**: historical surprise % alongside next-day price
    response per event.
  - **Capital returns**: forward dividend rate, yield, payout, DPS history.
  - **Financial statements**: IS / BS / CF quarterly with computed ratios
    (FCF, FCF margin, net debt, debt/equity, current ratio, interest
    coverage, ROIC).
- `src/app/pages/2_Universe.py`: **universe management**. Lists current
  universe (ticker, name, sector, added_at, last loaded_at, active flag).
  Form: "Add ticker" text input + button → calls `universe.add_ticker()`
  with a Streamlit spinner; success/failure toast. Each row has a "remove"
  button (soft delete) and a "refresh" button (re-run ingest for that
  ticker).
- All data reads go through a thin `src/app/queries.py` layer — **no raw
  SQL in page files**.
- Caching via `st.cache_data` keyed on `(ticker, warehouse_mtime)`.

**Done when**: user can open the app, browse the universe, click into a
ticker, see all panels populated, and add a new ticker through the UI in
under 30 seconds (including the backfill).

**Implementation notes**:
- `valuation_stats` (current vs. own median and percentile) is implemented
  as a Python function in `queries.py` operating on a fetched DataFrame,
  not SQL. DuckDB does not support `PERCENT_RANK() WITHIN GROUP` syntax.
- `pandas.Styler.background_gradient` requires `matplotlib`; added to deps.
- `pd.DataFrame.applymap()` removed in pandas 2.1 — use `.map()`.
- `load_dotenv()` must be called in Streamlit page files that trigger EODHD
  API calls; Streamlit doesn't inherit shell env vars reliably.

---

## Phase 6 — Daily forward snapshot

**Deliverable**: append-only collection of analyst expectations, running
routinely.

The schema and the section module already exist from Phase 1. This phase
wires up the daily routine and adds monitoring.

- Confirm `analyst_snapshot.py` correctly appends one
  `daily_forward_snapshot` row plus one `analyst_estimates_history` row per
  future period per snapshot day.
- Idempotency on the snapshot tables: re-running `load_daily.py` on the same
  calendar day overwrites that day's rows (via natural key
  `(ticker, snapshot_date)`), never duplicates.
- Add a "snapshot coverage" view on the Universe management page: how many
  days back does each ticker have analyst data? Helps detect ingestion gaps
  early.
- Cron / scheduling: document how to schedule `load_daily.py` (cron on
  Linux/macOS, Task Scheduler on Windows). Run after US market close
  (~17:00 ET).
- Tests:
  - Schema enforcement: missing analyst data results in a row with NULLs,
    not a failure.
  - Idempotency on same-day re-runs.

**Done when**: snapshot tables accumulate one row per ticker per calendar
day going forward; gap-detection report on the universe page is clean.

---

## Phase 7 — Trailing screens

**Deliverable**: a Screens page with filters that work without accumulated
history.

- `src/app/pages/3_Screens.py`: screen selector + parameter inputs.
- Implement, each as a parameterized function in `src/screens/`:
  - **Absolute valuation**: cheap on P/E, P/B, EV/EBITDA, FCF yield.
  - **Relative-to-own-history**: current multiple vs. own 3y/5y median as a
    percentile or z-score. (This screen exists because of the unlimited
    price history — it's a key MVP differentiator.)
  - **Growth**: Rev/EPS YoY thresholds + acceleration (last 4 quarters of
    YoY growth strictly increasing).
  - **Quality**: ROE, ROIC, margin expansion, FCF conversion > 80%.
  - **Balance sheet strength**: net debt/EBITDA, interest coverage, current
    ratio.
  - **Income**: yield + payout ratio cap + N-year dividend history from
    `dividends_annual`.
- Tests: each screen runs on the MVP universe fixture without error;
  spot-check the math on one criterion per screen.

**Done when**: user can pick a screen, tune thresholds, and see the universe
filtered live.

---

## Phase 8 — FX activation

**Deliverable**: the warehouse handles non-USD tickers correctly; USD
equivalents available throughout.

- DDL for `fx_rates_daily` (already in Phase 1 schema; loader is new).
- Loader for FX rates from chosen source (see open questions).
- USD-equivalent views: `prices_daily_usd`, `quarterly_fundamentals_usd`,
  etc. Native columns preserved alongside.
- UI toggle on the Home page: "show in USD" / "show in native currency".
- Test by adding a non-US ticker via the Universe page (e.g., `7203.TSE` for
  Toyota or an LSE name) and verifying both native and USD values render
  correctly.

**Done when**: an LSE or TSE ticker added via the universe page works
end-to-end with correct currency display.

---

## Phase 9 — Forward-looking screens

**Deliverable**: screens that exploit accumulated daily snapshots. **Requires
≥30 days of Phase 6 data before they produce signal.**

- Net rating upgrades over 7d / 30d / 90d windows.
- Target price raised by > X% over N days.
- Forward EPS estimate revised up (current FY, next FY) — uses
  `analyst_estimates_history`.
- Earnings beat-and-revise: positive surprise last quarter AND estimates
  raised since.
- Each screen is a query against `daily_forward_snapshot` +
  `analyst_estimates_history`, added to `src/screens/`.

**Done when**: user can answer "what changed this week in my universe?"

---

## Phase 10 — Sector view

**Deliverable**: aggregate page showing sector / industry medians with
drill-down.

- `src/app/pages/4_Sectors.py`: group by GIC sector and sub-industry. Show
  median multiples / growth / margins / yield. Click a row to see
  constituents.

**Done when**: useful as a starting point for "where are the cheap sectors
right now".

---

## Future (post-MVP, ordered loosely)

- Earnings calendar / events page (next 5 / 10 / 30 days reporting)
- Overnight digest of changes (new highs, rating moves, estimate revisions,
  upcoming earnings)
- Per-ticker watchlist annotations (your own notes in `universe.notes`)
- Backtesting harness combining screens + price history to evaluate signals
- True point-in-time prices via a corporate-actions table and re-derived
  adjustment factors (only if a backtest requires it)
- Bulk import of an index (e.g., S&P 500 constituents into the universe)
- Multi-user / authentication (currently single-user local)
- Migration off Streamlit if performance demands it

---

## Known limitations and risks

The following are **known issues we are NOT solving in the MVP**. They're
documented here so they don't come back as surprises, and so future phases
or refactors can address them deliberately rather than rediscovering them.
A coding agent encountering one of these in the wild should flag it rather
than paper over it.

### Debt classification ambiguity

EODHD's balance sheet exposes six overlapping debt-related fields:
`short_term_debt`, `long_term_debt`, `short_long_term_debt`,
`short_long_term_debt_total`, `long_term_debt_total`, and `net_debt`. Plus
related items like `capital_lease_obligations`. These do not always sum
cleanly, and the vendor's definitions are not always consistent across
companies or with how a given company reports in its own filings. Specific
known issues:

- **Operating lease debt** post-ASC 842 may or may not be included in
  long-term debt depending on the company.
- **Current portion of long-term debt** appears in both `short_term_debt`
  and inside `long_term_debt_total` for some tickers; subtracting blindly
  double-counts.
- **`net_debt`** is vendor-computed and we have no documentation on the
  exact formula. We store it but **derived net-debt fields in screens
  should compute it ourselves** from cash + short-term investments vs. total
  debt of choice — and the choice is what's ambiguous.

**Mitigation in MVP**: ratios like EV/EBITDA and net debt / EBITDA use a
single explicit formula (`long_term_debt_total + short_term_debt -
cash_and_short_term_investments`) documented in `src/compute/`. Screens
that depend on debt are tagged "approximate" in the UI. A future phase
addressing this would build a corrections layer keyed on
(ticker, fiscal_period_end) for hand-curated overrides.

### Sector-structure mismatches

The 64-field balance sheet, 34-field income statement, and 32-field cash
flow are modeled on a non-financial, non-real-estate company. Tickers
outside that mold produce mostly-NULL or misleading rows:

- **Banks and broker-dealers**: balance sheet is loans, deposits, and
  borrowings, not assets/liabilities in the operating sense. Fields like
  `inventory`, `accounts_payable`, `total_current_liabilities` are not
  meaningful. The income statement's `net_interest_income` is the headline
  number, not `gross_profit`. EBITDA is meaningless (interest is core
  operations, not a financing cost).
- **Insurers**: float and reserves dominate the liability side. Net income
  is volatile due to investment gains and reserve releases.
- **REITs**: depreciation is non-cash and arguably non-economic. FFO and
  AFFO matter more than net income or FCF. Standard P/E and FCF yield mean
  little.
- **Many non-US filers** report under IFRS with different line-item
  conventions and semi-annually rather than quarterly.

**Mitigation in MVP**: the MVP universe is intentionally all tech /
consumer / media. No banks, insurers, or REITs. When tickers from these
sectors are added later, expect: (a) many NULL fields, (b) some derived
ratios (current ratio, EBITDA-based multiples) showing as N/A or
nonsensical, and (c) the deep-dive page showing the data faithfully but
without sector-specific transformations.

A future phase to address this would add a `sector_template` concept that
swaps the deep-dive panels and the screen list based on
`security_master.gic_sector` (e.g., bank-specific panels for net interest
margin, NPL ratios, tier-1 capital; REIT-specific panels for FFO/AFFO).

### Other known limitations

- **Restatements**: handled via `loaded_at` but we do not alert when one
  occurs. Current design uses in-place updates keyed by natural keys (latest
  value retained; prior values not kept as separate versions). A future phase
  could surface "restated since last load" as a flag on the deep-dive page.
- **Multiple share classes**: GOOG vs. GOOGL are separate tickers in EODHD.
  We do not collapse them. The user is expected to pick the class they want.
- **Pre-IPO and short-history tickers**: CRWD (2019) and U (2020) have
  limited historical multiples. Relative-to-own-history screens may produce
  meaningless percentiles for very young tickers; consider gating on
  minimum-history thresholds in Phase 7.
- **Spin-offs and major mergers**: the price series before such events
  reflects the predecessor entity. The vendor's adjusted_close may or may
  not handle this cleanly; cross-check is a manual exercise per case.
- **`adjusted_close` replacement semantics**: the Phase 2 price ingestion uses
  `UPSERT` for all price columns including `adjusted_close`. Because we always
  download the full price history on every load, this is functionally
  equivalent to the "strict full-column replacement" pattern described in the
  ingestion model. If the vendor ever truncates or corrects the date range of
  the returned series, stale rows for removed dates would retain their old
  `adjusted_close` values. Address this with a DELETE-then-INSERT or
  DELETE-orphan approach if it ever surfaces in practice.
- **Vendor client tests use mocks, not VCR cassettes**: Phase 2 retry/error
  tests use `unittest.mock.patch` on `httpx.get` rather than recorded HTTP
  fixtures. This is sufficient for testing request construction and retry
  logic; API contract drift would require a separate acceptance test against
  the live API or manually recorded cassettes.

---

## Open questions (resolve before relevant phase)

| Question | Needed before | Default if undecided |
|---|---|---|
| EODHD subscription tier / rate limits | Phase 2 | check EODHD account settings; throttle conservatively (e.g., 5 req/s) |
| Archive every daily raw file, or just keep the latest? | Phase 2 | archive for first 90 days, then purge; flag in `settings.yml` |
| Beta benchmark: SPY only, or also per-region (TPX, EWU)? | ~~Phase 4~~ RESOLVED | SPY via `prices_daily`; add via `add_ticker("SPY")`. Per-region deferred to Phase 8. |
| FX rate source — EODHD, ECB, Yahoo? | Phase 8 | EODHD if available (single vendor); else ECB |
| Forward-snapshot retention — keep forever, or roll off after N years? | when table grows large | keep forever; revisit at 5 GB |
| `analyst_estimates_history` — snapshot daily, or only on changes? | Phase 6 | daily for simplicity; can compress later by collapsing unchanged runs |
| Should `remove_ticker` ever hard-delete? | Phase 3 | no; soft delete only. Provide a separate `purge_ticker` utility if ever needed |
| Net debt formula for screens — which fields, exactly? | ~~Phase 4~~ RESOLVED | `long_term_debt_total + short_term_debt - cash_and_short_term_investments`; see `src/compute/multiples.py` |

---

## How to use this plan

- **One phase at a time**. Don't start Phase 5 with Phase 4 half-done.
- **Each phase ends with a runnable system**. If you can't demo something
  new at the end of a phase, the phase isn't done.
- **Tests gate completion**. A phase isn't done if its tests aren't.
- **Document deviations**. If you change a design decision mid-build, update
  AGENTS.md in the same commit. The two files must stay coherent.
