# PLAN.md

> Backlog and forward plan. The phased build-out is **done**. New work is
> tracked on a Jira board; this file holds the inventory of what shipped,
> ideas not yet ticketed, and decisions that should outlive any single
> ticket. See `AGENTS.md` for design principles and `REVIEW.md` for the
> end-of-phase code review.

## Status

**Phases 0 through 13: complete.** The system is production-ready for
personal use. As of the latest load: 507 active tickers, 330 MB
warehouse, 221 tests passing in ~19 s, Phase 13B snapshot history
accumulating daily.

## What shipped

| Phase | Deliverable | Key files |
|---|---|---|
| 0 | Project setup, deps, lint, test scaffolding | `pyproject.toml`, `tests/test_smoke.py` |
| 1 | Schema + per-section parsers | `src/schema/migrations/001_initial.sql`, `src/ingest/sections/*.py` |
| 2 | EODHD client + price ingestion | `src/ingest/fetch.py`, `src/ingest/sections/prices.py` |
| 3 | Universe CLI | `src/universe.py`, `scripts/{add_ticker,seed_universe,load_daily}.py` |
| 4 | Computed multiples + technicals views | `src/compute/{ttm,multiples,technicals}.py` |
| 5 | MVP Streamlit UI (Home + Deep Dive + Universe) | `src/app/Home.py`, `src/app/pages/1_Deep_Dive.py`, `src/app/queries.py` |
| 6 | Daily forward snapshot + analyst gauge | `src/ingest/sections/analyst_snapshot.py`, Deep Dive Analyst tab |
| 7 | Trailing screens (6 of them) | `src/screens/trailing.py`, `src/app/pages/3_Screens.py` |
| 8 | Sector view + bulk ticker upload | `src/screens/sectors.py`, `src/app/pages/5_Sectors.py` |
| 9 | Docker, rate-limited resumable bulk loader, `load_runs` monitoring | `Dockerfile`, `docker-compose.yml`, `Makefile`, `src/ingest/bulk.py`, `scripts/bulk_load.py`, migration 002 |
| 10 | Watchlists + display/comparison-set discipline | `src/watchlist.py`, `src/app/pages/4_Watchlists.py`, `src/app/sidebar.py`, migration 003 |
| 11 | Annual statements + period/depth/units toggles | `src/ingest/sections/financials.py`, `src/app/queries.py:statement`, migration 004 |
| 12 | Universe drill-down modal with paginated prices + fundamentals | `_drill_down_dialog` in `2_Universe.py`, `queries.prices_page` / `prices_count` |
| 13A | Vendor-trend forward screens (EPS revised up, net upward revisions, beat-and-raise) | `src/screens/forward_vendor.py`, migration 005 |
| 13B | Snapshot-history forward screens (consensus rating shift, target price raised) | `src/screens/forward_history.py`, `src/app/pages/6_Forward_Screens.py` |

## Cleanup backlog (from REVIEW.md)

All items addressed in the post-review cleanup pass. See REVIEW.md §0 for
the per-item status table. Remaining items below are still-pending,
deferred to Jira.

- **`5_Sectors.py` N+1 query on cold cache** — single grouped query
  instead of N per-sector queries. Cached path is fine.
- **`2_Universe.py` per-ticker buttons** — at 500+ tickers the rerender
  is sluggish. Paginate the table or move actions to a side panel.
- **`_apply_units` in `1_Deep_Dive.py`** — hard-codes `$` prefix.
  Replace with `security_master.currency_code` once non-US tickers
  land.
- **`screen_growth` strict acceleration ordering** — `g1>g2>g3>g4` breaks
  on a single flat quarter. Consider a "non-decreasing with slack"
  variant.
- **`bulk_load.py --resume` UUID job-id** — accept a short unique
  prefix to reduce copy-paste friction.

## Open backlog (move to Jira when ready)

### Quick wins
- "Save current screen filters" (not just the ticker list) so a saved
  watchlist can be re-evaluated later. Schema reservation already noted
  in AGENTS.md.
- Sortable / filterable Universe management table — at 500+ tickers the
  current per-row buttons are sluggish.
- Earnings calendar page: upcoming `earnings_events` rows with
  `eps_actual IS NULL`, grouped by week.
- Per-ticker notes editing on the Universe page (the column exists; no
  edit UI yet).
- Show currency in the Deep Dive numbers — replace hard-coded `$` with
  `security_master.currency_code`.
- "Compare two tickers" mode on the Deep Dive page — pick a second
  ticker, render both columns side by side.

### Medium effort
- **Portfolio mode**: populate `watchlist_membership.shares` /
  `cost_basis`; compute position value, weight, gain/loss, sector
  allocation against `prices_daily.adjusted_close`. No new schema needed.
- **Country-scoped comparison sets**. Parameterize `comparison_set`
  construction (`"universe" | "country" | "sector"`). Schema already
  supports it.
- **Sector-template UI** — different statement summaries for banks,
  insurers, REITs (interest income vs. revenue, net premiums vs. gross
  profit, FFO vs. net income).
- **Overnight digest**: a script that builds a Markdown summary of the
  day's changes (new highs/lows, rating moves, estimate revisions,
  upcoming earnings) and emails or writes to a file.
- **Backtesting harness**: combine a screen + price history to compute
  historical screen performance. The point-in-time integrity is already
  in place.

### Larger
- **True point-in-time prices**: a corporate-actions table (splits +
  dividends with ex-dates) + on-the-fly adjustment-factor derivation.
  Needed for any serious backtest.
- **FX activation (originally Phase 14)**: FX-rate loader, USD-equivalent
  views (`prices_daily_usd`, `quarterly_fundamentals_usd`), Home page
  USD/native toggle. Trigger when the first non-US ticker is added.
- **EC2 deployment**: same Docker setup; add EBS volume for `data/` and
  systemd timer.
- **S&P 500 / Russell 1000 constituent importer** with a tracker for
  joiners/leavers.
- **Multi-user / authentication**.

## Decision log

Decisions that should outlive any single Jira ticket. (Phase-by-phase
"resolved open questions" from the previous version of this file have
been folded into `AGENTS.md` as design principles and conventions.)

- **Watchlists are snapshots, not dynamic.** A watchlist created from a
  screen result freezes the ticker list at save time. Re-save to refresh.
- **Filter-parameter capture for "rebuild watchlist from filter"** is
  explicit future work, not free-form.
- **Comparison set = full active universe** by default. Display set is
  what the watchlist sidebar filters. Tests pin the invariant.
- **`add_ticker` writes a pending `active=false` row before ingest.** On
  ingest failure for a brand-new ticker the row is deleted. Existing
  tickers keep their row regardless of failure.
- **Universe seed YAML is read only by `seed_universe.py`.** Runtime
  source of truth is the `universe` table.
- **Soft delete only.** Removing a ticker sets `active=false`; history
  stays.
- **`config/settings.yml:bulk_load.requests_per_minute`** is 500
  (post-tuning, paid EODHD plan). Tune downward for the free tier.
- **DuckDB single-writer constraint** is mitigated by scheduling the
  cron load at 02:00 local. Read-only Streamlit mode is on the backlog
  if option 1 ever proves painful.
- **Net debt** = `long_term_debt_total + short_term_debt -
  cash_and_short_term_investments`, COALESCE missing components to 0.
- **Beta benchmark** = `config/settings.yml:benchmark.ticker` (default
  `SPY.US`). Per-region benchmarks deferred.
- **TTM timing** is unified on `earnings_events.report_date`. All four
  TTM views join on `(ticker, fiscal_period_end)` to source it.
- **Revenue-revision counts** are NOT in EODHD's `Earnings.Trend`. Only
  EPS revisions are surfaced.
- **`eps_trend_30days_ago == 0`** rows are excluded before computing
  the % delta to avoid infinite values.
- **Daily snapshot retention**: keep forever. Revisit at 5 GB.
- **Archive of raw JSON files**: keep 90 days then purge
  (`ingest.archive_retention_days` in settings).
- **`fetch._get` retry policy**: 4 attempts, exponential backoff
  starting at 1 s, retries 429 + 5xx + transport errors, no retry on
  200-with-Error (terminal — vendor is telling us the ticker is bad).

## How to use this file going forward

- This file is no longer the work plan — Jira is. Use this file for:
  - the "what shipped" inventory above,
  - cleanup items not yet ticketed,
  - design decisions that should outlive any single ticket.
- AGENTS.md remains the living design document — update it whenever a
  ticket changes a convention or resolves a previously-open question.
- REVIEW.md is a point-in-time snapshot; replace it when a similar
  end-of-stretch review is useful again.
