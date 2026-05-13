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
(designed-in but not loaded until later).

---

## Phase 0 — Project setup ✓ DONE

(Setup details unchanged from original plan; see git history.)

---

## Phase 1 — Schema and section parsers ✓ DONE

(Details unchanged; see git history. Note: the financials section parser
currently ingests `Financials.*.quarterly` only. Annual ingestion is added in
Phase 11.)

---

## Phase 2 — Vendor client + price ingestion ✓ DONE

(Details unchanged; see git history.)

---

## Phase 3 — Universe management (CLI) ✓ DONE

(Details unchanged; see git history.)

---

## Phase 4 — Computed multiples and technicals ✓ DONE

**Implementation notes**:
- TTM revenue, EBITDA, and FCF views were initially using the statement
  table's own `report_date`; corrected to join `earnings_events` on
  `(ticker, fiscal_period_end)` so all TTM views share one timing source.
- Beta benchmark hardcoded to `'SPY'` was corrected to read
  `benchmark.ticker` from `config/settings.yml` (value: `SPY.US`).

---

## Phase 5 — MVP UI ✓ DONE

**Implementation notes**:
- `valuation_stats` (current vs. own median and percentile) is implemented
  as a Python function in `queries.py` operating on a fetched DataFrame.
- `pandas.Styler.background_gradient` requires `matplotlib`; added to deps.
- `load_dotenv()` must be called in Streamlit page files that trigger EODHD
  API calls.

---

## Phase 6 — Daily forward snapshot ✓ DONE

**Implementation notes**:
- `next_period_end` replaces `next_earnings` on the Deep Dive header.
- Streamlit width API: `width="stretch"` replaces deprecated
  `use_container_width=True`.
- EODHD error responses validated at the fetch layer; warehouse path
  centralized in `src/schema/runner.py`.

---

## Phase 7 — Trailing screens ✓ DONE

(Phase 7 decisions retained from original plan: SQL in `src/screens/trailing.py`,
fetch-then-filter in Python for optional parameters, `PERCENT_RANK() OVER
(PARTITION BY ticker ORDER BY ...)` for relative history, ROIC formula and
margin-expansion / FCF-conversion definitions as previously documented.)

---

## Phase 8 — Sector view + bulk ticker upload ✓ DONE

(Sector aggregates page implemented; bulk-add textarea and `.txt` file upload
implemented in `src/app/pages/2_Universe.py` calling `bulk_add_tickers`.)

---

## Phase 9 — Operational hardening, Docker, and bulk universe load ✓ DONE

**Deliverable**: a containerized, rate-limited, resumable bulk loader; a
scheduled daily refresh running on local cron; the production universe
(500+ tickers) fully loaded; per-ticker load monitoring visible in the UI.

This phase makes the system usable at scale. The existing bulk-add and daily
load work for 10 tickers but will break or timeout silently at 500. Fix that,
then load the real universe.

### Shared ticker-input parser

The current bulk-add parser lives inline in `2_Universe.py`. Extract to
`src/ticker_input.py` as a pure function: `parse_ticker_input(raw_text: str)
-> list[str]`. Handles textarea pastes and file content uniformly: strips
whitespace-only lines, ignores `#`-prefixed lines, returns canonicalized
ticker strings. Reused in Phase 10 for watchlist creation from file.

### Rate-limited, resumable bulk loader

- New module `src/ingest/bulk.py` wrapping `add_ticker` for batch use.
- Throttling: configurable requests-per-minute and requests-per-day in
  `config/settings.yml` under `eodhd.rate_limit`. Default conservative (e.g.,
  20 RPM) until the user's tier is confirmed.
- Retry with exponential backoff on HTTP 5xx and connection errors; surface
  EODHD's 200-with-Error responses as terminal (no retry).
- Checkpointing: a `bulk_load_jobs` table tracks in-progress batches with
  per-ticker status (`pending` / `ok` / `failed`). Resume reads pending rows
  and continues. Restart-safe by design.
- CLI: `uv run python scripts/bulk_load.py --file tickers.txt` and
  `--resume <job_id>`.

### Per-ticker load monitoring

- New table `load_runs`: one row per (ticker, run_started_at) with status,
  duration_ms, error_message. Populated from both `load_daily.py` and
  `bulk_load.py` via a shared decorator/helper.
- Universe management page (`src/app/pages/2_Universe.py`) gains two
  columns:
  - **Last load**: timestamp of most recent successful load
  - **Status**: `ok` / `failed (<error>)` / `stale (>2 days)`
- Also adds **price start** and **price end** columns (the small item from
  the original Phase 9), since price-date visibility is part of "monitoring."

### Docker

- `Dockerfile`: Python 3.11-slim base, installs `uv`, copies repo, no
  entrypoint (commands supplied at run-time).
- `docker-compose.yml`: two services.
  - `app`: one-shot service for ingest scripts. `docker compose run --rm app
    uv run python scripts/load_daily.py`
  - `streamlit`: long-running UI service on port 8501.
  - Both mount `./data:/app/data` and `./.env:/app/.env:ro`.
- `Makefile` (or `scripts/docker-helpers.sh`) with shortcuts: `make load`,
  `make ui`, `make shell`.

### DuckDB concurrency

DuckDB allows one writer at a time. If Streamlit holds the warehouse open
while `load_daily.py` runs, the load fails. Two options:

1. **Schedule loads outside UI hours** (cron at 02:00 local). Simplest;
   ship this as default.
2. **Streamlit opens read-only**, reconnects on each request. Cleaner but
   more changes. Defer unless option 1 proves painful.

Phase 9 ships option 1. Document the constraint in `AGENTS.md`.

### Local cron

- Sample crontab snippet committed to `scripts/cron.example`:
  ```
  0 2 * * 1-5 cd /path/to/project && docker compose run --rm app \
      uv run python scripts/load_daily.py >> data/logs/cron.log 2>&1
  ```
- Documented in README.

### EC2 readiness (preparation, not deployment)

- Confirm the Docker setup runs cleanly with only `.env` + `data/` mounted
  (no other host-specific paths).
- README section: "deploying to EC2" — points to the same `docker compose`
  setup, plus notes on EBS volume for `data/` and `systemd` timers as a
  cron alternative.
- Actual EC2 deployment is post-MVP.

### Bulk-load the production universe

End-of-phase deliverable: the user supplies a `.txt` file of 500+ tickers,
runs `scripts/bulk_load.py --file <file>`, and walks away. The job
completes (over hours, given rate limits), the universe table fills, and
the daily refresh starts accumulating snapshots from day 1.

### Tests

- `parse_ticker_input` handles textarea, file content, comments, blanks
  identically.
- Rate limiter respects configured RPM under load.
- Checkpoint resume: kill a bulk load mid-run, restart with `--resume
  <job_id>`, all remaining tickers complete; no duplicates in `universe`.
- `load_runs` table populated by both `load_daily.py` and `bulk_load.py`.
- Universe page shows last-load and price-range columns correctly.
- Docker: `docker compose run --rm app uv run pytest` passes.

**Done when**: the production universe is loaded; the daily refresh runs on
cron via Docker; the Universe page surfaces load status for every ticker.

---

## Phase 10 — Watchlists and portfolios (schema)

**Deliverable**: users can group subsets of the universe into named
watchlists, optionally attach share counts (portfolio mode), select an
active watchlist that scopes screen displays — while keeping all
median/percentile/comparison calculations on the full universe.

### Schema

```sql
CREATE TABLE watchlist (
    watchlist_id INTEGER PRIMARY KEY,
    name VARCHAR UNIQUE NOT NULL,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE watchlist_membership (
    watchlist_id INTEGER REFERENCES watchlist(watchlist_id) ON DELETE CASCADE,
    ticker VARCHAR REFERENCES universe(ticker),
    shares DOUBLE,            -- nullable; for portfolio mode (Phase 10.5+)
    cost_basis DOUBLE,        -- nullable; per share (Phase 10.5+)
    notes VARCHAR,
    added_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (watchlist_id, ticker)
);
```

`shares` and `cost_basis` are present from day 1 but unused by Phase 10 UI.
Portfolio calculations (current value, weights, gain/loss, tax lots) come
in a later sub-phase or as Jira items. The schema is laid down now so we
don't migrate later.

### Snapshot semantics (resolved)

Watchlists are **snapshots**: when created, the membership ticker list is
materialized into `watchlist_membership` and does not auto-update. To get
updated members from a filter, the user re-saves.

### Functionality

- `src/watchlist.py`:
  - `create_watchlist(con, name, tickers, description=None)`
  - `delete_watchlist(con, name_or_id)`
  - `rename_watchlist(con, old_name, new_name)`
  - `list_watchlists(con)`
  - `get_membership(con, watchlist_id_or_name) -> list[str]`
- File upload for watchlist creation uses `src/ticker_input.py` from Phase
  9 — identical semantics to bulk universe upload.
- New page `src/app/pages/4_Watchlists.py`:
  - List existing watchlists with member count, created date, delete button.
  - Create form: name + (paste tickers / upload file).
  - Single-watchlist view: shows current members with values.
- "Save current view as watchlist" button on every screen page and on the
  sector view. Captures the currently-filtered ticker list with a single
  click; user names it on save.
- Active-watchlist selector: a sidebar widget (`st.selectbox` in
  `src/app/Home.py` sidebar) with persistent state via `st.session_state`.
  Defaults to "Full universe."

### Screen refactor: display set vs. comparison set

The critical invariant: medians, percentiles, sector aggregates, and any
distribution-based calculation use the **comparison set** (full active
universe). The **display set** (active watchlist or full universe) only
filters which rows the user sees.

- `queries.py` functions that compute medians/percentiles take an explicit
  `comparison_set: list[str] | None = None` argument (None = full active
  universe). They take a separate `display_filter: list[str] | None`.
- All page files pass `display_filter = active_watchlist_members or None`
  and leave `comparison_set` at its default.
- Sector view: filters displayed tickers by watchlist but computes
  per-sector medians over the full universe.

### Country-scoped comparisons (future preparation, not built)

When non-US tickers are added (Phase 14 FX activation), users may want to
compare a Japanese tech name against Japanese tech medians rather than the
global universe. `security_master` already stores country, so no schema
change needed. Comparison-set construction will be parameterized in a
future Jira item; for now, comparison set = full active universe.

### Tests

- Watchlist CRUD round-trips.
- File-upload watchlist creation uses the same parser as bulk universe
  upload (regression test: identical input produces identical ticker list).
- "Save current screen as watchlist" captures exactly the displayed
  tickers.
- Delete cascades: removing a watchlist removes its membership rows.
- Screen behavior with active watchlist: display set is filtered;
  medians/percentiles are unchanged from the full-universe case.
- Sector view: per-sector medians identical before and after watchlist
  selection; only the visible constituents change.

**Done when**: user can create, populate (typed/uploaded), and delete
watchlists; the active watchlist scopes display across all screens; medians
and sector aggregates remain anchored to the full universe.

---

## Phase 11 — Annual statements + Statements view options

**Deliverable**: the warehouse holds both quarterly and annual statements;
the Deep Dive Statements panel offers period (annual/quarterly), depth
(summary/full), and units (B/M/K/raw) toggles.

The fundamentals JSON already contains `Financials.*.yearly` arrays
alongside `.quarterly`, but the Phase 1 parser only reads `.quarterly`. This
phase adds annual ingestion and the corresponding UI controls.

### Schema migration

`src/schema/migrations/002_statements_period_type.sql`:

- ALTER TABLE on `income_statement`, `balance_sheet`, `cash_flow` to add
  `period_type VARCHAR NOT NULL DEFAULT 'quarterly'`.
- Drop old primary key, add new key on `(ticker, fiscal_period_end,
  period_type)`. Necessary because annual Q4 fiscal-period-end may collide
  with quarterly Q4 fiscal-period-end for the same date.
- Backfill: existing rows default to `period_type = 'quarterly'`.

### Parser update

`src/ingest/sections/financials.py`:

- Read both `.quarterly` and `.yearly` arrays.
- Same field-name normalization (camelCase → snake_case, including the two
  vendor typos already handled).
- Annual rows written with `period_type = 'annual'`.
- Annual `report_date` comes from `filing_date` of the annual filing — note
  this differs from the Q4 quarterly `report_date`.

### Re-ingest to backfill annual data

After the migration ships, run the bulk loader (Phase 9) over the existing
universe to populate annual rows for every ticker. Built-in idempotency
makes this safe: quarterly rows are untouched, annual rows fill in.

### UI

Deep Dive Statements panel gains three controls:

1. **Period**: Annual | Quarterly (default: Quarterly — current behavior)
2. **Depth**: Summary | Full (default: Summary — current behavior)
3. **Units**: Billions | Millions | Thousands | Raw (default: Billions —
   current behavior)

- "Summary" = the existing curated column list per statement type.
- "Full" = every snake_case column in the table for that statement type.
  Many will be NULL for any given ticker; that's expected and acceptable
  (documented in `AGENTS.md` "Sector-structure mismatches").
- Units divide displayed values by 1e9 / 1e6 / 1e3 / 1, with a unit suffix
  in the column header.

### Query layer

- `queries.statement(ticker, statement_type, period_type, depth) ->
  DataFrame` returns the appropriate rows + columns for the toggle state.
- Display unit conversion happens in the page (or a small helper), not in
  SQL, so the underlying data view is canonical.

### Tests

- Annual ingestion: AAPL fixture extended with `.yearly` block produces
  `period_type = 'annual'` rows.
- Migration runs cleanly on the existing warehouse (no data loss in
  quarterly rows).
- Toggle combinations: each of the 16 combinations of period × depth × units
  renders without error on a populated ticker.
- Unit math: a known value of 1.234e9 displays as 1.23 (Billions), 1234.00
  (Millions), 1234000.00 (Thousands), 1234000000 (Raw).
- "Full" view shows columns that "Summary" hides; "Summary" doesn't drop
  required columns (revenue, net income, total assets, etc.).

**Done when**: user can switch the Statements panel to annual view, see the
full statement, and read it in Millions — without page refresh — and the
underlying tables hold both periods.

---

## Phase 12 — Universe-manager drill-down (modal)

**Deliverable**: clicking a row on the Universe management page opens a
modal showing the underlying price history and fundamentals for that ticker,
read-only, paginated to avoid loading decades of data at once.

### UI

- Use `st.dialog` (Streamlit 1.34+) for the modal. Triggered by a button
  per universe row (or a clickable cell, depending on Streamlit table
  affordances at the time).
- Two tabs inside the dialog:
  - **Prices** (priority): paginated OHLCV + adjusted close.
  - **Fundamentals**: latest quarterly and annual rows from IS/BS/CF, plus
    `earnings_events` and `shares_outstanding` recent rows.

### Prices tab

- Default 100 rows per page, sorted descending by date.
- Page-size selector: 50 / 100 / 250 / 500.
- Pagination controls: prev / next / jump-to-page.
- Optional date-range filter (`from` / `to` date pickers) — if set,
  pagination operates on the filtered range.
- Columns: `date`, `open`, `high`, `low`, `close`, `adjusted_close`,
  `volume`. Numbers in raw units (no Billions conversion — these are share
  prices and counts).

### Fundamentals tab

- Three sub-sections (IS / BS / CF) with toggle for quarterly vs annual,
  reusing the Phase 11 query helpers.
- Default: most recent 8 quarterly periods or 5 annual periods.
- Read-only display only.

### Query layer

- `queries.prices_page(ticker, page_size, offset, date_from=None,
  date_to=None) -> DataFrame`. SQL uses `LIMIT ... OFFSET ...` on
  `prices_daily`, ordered by date desc. Existing `(ticker, date)` index
  makes this O(log n).
- `queries.prices_count(ticker, date_from=None, date_to=None) -> int` for
  total-page calculation.
- `queries.fundamentals_recent(ticker, statement_type, period_type, n=8)`.

### Tests

- Pagination math: page 2 of size 100 returns rows 101–200.
- Date-range filter intersects correctly with pagination.
- Empty results (e.g., a brand-new ticker with no price load yet) render
  without error.
- Memory: opening the dialog for AAPL (~12,000 trading days) loads only
  the current page, not the full history.

**Done when**: user clicks a universe row, sees a modal with paginated
prices in <500ms, and can flip to fundamentals without re-fetching prices.

---

## Phase 13 — Forward-looking screens

**Deliverable**: a Forward Screens page with screens grouped into "Vendor
trends (works immediately)" and "Snapshot history (≥30 days)."

The vendor's `Earnings.Trend` block carries pre-computed 7-day and 30-day
deltas for EPS and revenue estimates per future fiscal period. These power
revision-tracking screens *without* needing our own accumulated snapshot
history. Rating-change screens still need accumulated `daily_forward_snapshot`
data because EODHD's `AnalystRatings` is point-in-time only.

### Phase 13A — Vendor-trend screens (works immediately)

**Verify column coverage first.** Before building screens, check that
`analyst_estimates_history` (per Phase 1 parser) actually persists these
fields from `Earnings.Trend`:

- `eps_trend_current`, `eps_trend_7days_ago`, `eps_trend_30days_ago`,
  `eps_trend_60days_ago`, `eps_trend_90days_ago`
- `eps_revisions_up_last_7days`, `eps_revisions_up_last_30days`,
  `eps_revisions_down_last_7days`, `eps_revisions_down_last_30days`
- Same set of fields for revenue.

If any are missing, ship a schema migration to add them and re-ingest. The
fields are zero-cost to store and the only blocker to vendor-trend screens.

**Screens** (each as a parameterized function in
`src/screens/forward_vendor.py`):

- **EPS estimate revised up over 7d / 30d**: filters tickers where
  `eps_trend_current > eps_trend_30days_ago` by at least a configurable
  threshold, optionally scoped to a specific future-period bucket (e.g.,
  next quarter, current FY, next FY).
- **Revenue estimate revised up over 7d / 30d**: analog of the above.
- **Net upward EPS revisions**: `eps_revisions_up_last_30days -
  eps_revisions_down_last_30days >= N`, with N tunable.
- **Beat-and-revise**: positive surprise in latest `earnings_events` AND
  current EPS estimate > 30-days-ago estimate for the next period.

### Phase 13B — Snapshot-history screens (works after ~30 days)

- **Consensus rating shift over N days**: difference between latest
  `daily_forward_snapshot.consensus_rating` and N-days-ago value. Surface
  tickers with >0.5 rating-point shift up or down.
- **Target price raised by > X% over N days**: same idea against
  `target_price`.
- Both gated by a per-ticker "days of snapshot history" check; tickers below
  the threshold are excluded with a count surfaced ("3 tickers have
  insufficient history").

### UI

- New page `src/app/pages/5_Forward_Screens.py`. Screens grouped under two
  headers: "Vendor trends" and "Snapshot history (≥30 days)."
- Same display-set / comparison-set discipline from Phase 10: an active
  watchlist filters which results are shown, not which tickers are
  scanned.
- "Save as watchlist" button (per Phase 10).

### Tests

- 13A: each vendor-trend screen runs against the loaded universe and
  produces sane results; threshold parameters change result counts
  monotonically.
- 13A: column-presence check passes after the migration (every required
  field is non-null for at least one recent ticker-period pair).
- 13B: insufficient-history gate excludes tickers correctly and reports
  the count.
- Watchlist interaction: 13A and 13B both respect the active watchlist for
  display but never for comparison.

**Done when**: 13A screens are immediately useful on day 1 of the phase;
13B screens are wired up and waiting for the snapshot table to accumulate
30+ days for the relevant tickers.

---

## Phase 14 — FX activation (deferred)

**Deliverable**: non-USD tickers work end-to-end with both native and USD
presentations.

Triggered only when the user wants to add a non-US ticker. Unchanged from
the original Phase 10 plan: FX rate loader, USD-equivalent views
(`prices_daily_usd`, `quarterly_fundamentals_usd`, etc.), Home page toggle
"USD" / "native," and an acceptance test on an LSE or TSE ticker.

---

## Transition to Jira

After Phase 13 (and possibly Phase 14, if non-US tickers come up), new
work moves to a Jira board rather than PLAN.md. The criterion is rough:

- **Stays in PLAN.md**: anything touching the schema, the ingestion model,
  or a whole new section of the UI.
- **Goes to Jira**: UI tweaks, additional screen variants, performance
  improvements, individual bug fixes, sector-template work, alerts/digests,
  per-ticker watchlist annotations, backtesting harness.

PLAN.md remains as the historical record. AGENTS.md continues to be the
living design document and gets updated whenever a phase resolves an
open question or introduces a new convention.

---

## Future (post-MVP, ordered loosely)

- Portfolio calculations on watchlists with `shares` populated (current
  value, weight, gain/loss, sector allocation)
- Country-scoped or region-scoped comparison sets (medians within country
  rather than global)
- Sector-template UI (per AGENTS.md "Sector-structure mismatches")
- Earnings calendar / events page
- Overnight digest of changes (new highs, rating moves, estimate revisions,
  upcoming earnings)
- Backtesting harness combining screens + price history
- True point-in-time prices via corporate-actions table
- S&P 500 / Russell 1000 constituent importer (if maintenance of static
  uploads becomes tedious)
- EC2 deployment (Docker setup from Phase 9 carries over)
- Multi-user / authentication

---

## Known limitations and risks

(Original list retained: debt classification ambiguity; sector-structure
mismatches for banks/insurers/REITs; restatement detection; multiple share
classes; pre-IPO short history; spin-offs; adjusted_close replacement
semantics; vendor client tests use mocks not VCR.)

### Additional limitations introduced by post-MVP phases

- **Watchlists are snapshots, not dynamic** (Phase 10). A watchlist created
  from a screen result is frozen at creation time. If the underlying screen
  result drifts (new earnings, price changes), the watchlist does not
  update automatically. Re-save to refresh. Documented as expected behavior.
- **Country-scoped comparisons not implemented** (Phase 10 / 14). All
  median, percentile, and sector calculations use the full active universe
  regardless of country. When non-US tickers are added this may produce
  noisy comparisons (e.g., a Japanese REIT vs. a US REIT). Schema supports
  the future refactor; the change is in `queries.py` only.
- **Annual statements may double-count quarters** in naive joins (Phase
  11). Any query joining `income_statement` to itself or to other statement
  tables must filter on `period_type` explicitly. Documented in
  `AGENTS.md`; query helpers in `queries.py` always set period_type.
- **DuckDB single-writer constraint** (Phase 9). The cron load is scheduled
  outside UI hours by default. If the user opens Streamlit during the
  scheduled load, the load fails. Surface this as a clear error in the
  `load_runs` table.
- **EODHD rate-limit assumptions** (Phase 9). Conservative defaults pending
  confirmation of subscription tier. Adjust `config/settings.yml` once the
  tier is known.

---

## Open questions (resolve before relevant phase)

| Question | Needed before | Default if undecided |
|---|---|---|
| EODHD subscription tier / rate limits | Phase 9 (load 500+) | conservative throttle: 20 RPM; adjust upward after first successful bulk load |
| Archive every daily raw file, or just keep the latest? | Phase 9 | archive for first 90 days, then purge; flag in `settings.yml` |
| Docker base image | Phase 9 | `python:3.11-slim` |
| Cron timing for daily load | Phase 9 | 02:00 local (quiet hours, avoids UI overlap) |
| Should "save as watchlist" capture filter parameters too (for re-evaluation later) or just the ticker list? | Phase 10 | ticker list only; "rebuild watchlist from filter" deferred as future work |
| Watchlist names: case-sensitive uniqueness? | Phase 10 | case-insensitive uniqueness; store as user-entered, compare lowered |
| FX rate source — EODHD, ECB, Yahoo? | Phase 14 | EODHD if available; else ECB |
| Forward-snapshot retention — keep forever, or roll off after N years? | when table grows large | keep forever; revisit at 5 GB |

(Resolved questions from earlier phases retained: beta benchmark = SPY via
`add_ticker("SPY")`; net debt formula = `long_term_debt_total +
short_term_debt - cash_and_short_term_investments`; analyst_estimates_history
daily snapshot frequency = daily for simplicity; `remove_ticker` is soft
delete only.)

---

## How to use this plan

- **One phase at a time**. Don't start Phase 11 with Phase 10 half-done.
- **Each phase ends with a runnable system**. If you can't demo something
  new at the end of a phase, the phase isn't done.
- **Tests gate completion**. A phase isn't done if its tests aren't.
- **Document deviations**. If you change a design decision mid-build, update
  AGENTS.md in the same commit. The two files must stay coherent.
- **From Phase 9 onward, prefer testing against the loaded production
  universe** (500+ tickers). Performance issues, edge cases, and
  sector-structure mismatches surface there that the 10-ticker fixture
  hides.
