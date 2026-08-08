# PLAN.md

> Forward plan and backlog. `AGENTS.md` is the living design document —
> read it first. `REVIEW.md` is a point-in-time code review (May 2026).
> `CODE_TUTORIAL.md` is the guided tour for a new reader.
>
> Last re-baselined: **2026-08-08**.

## 1. Where the project actually stands

The phased build (0–13) and a first round of Jira tickets (INV-1 … INV-7)
are **complete**. The codebase is healthy: 253 tests passing in ~24 s,
migrations through `007`, seven working pages, all four mission modes
delivered.

The problem is not the code. **The system stopped running.**

| Signal | Value | Implication |
|---|---|---|
| Latest price bar | 2026-05-18 | ~82 days stale |
| Days the daily loader has ever run | 4 (May 12, 13, 18, 19) | never automated |
| `crontab` / launchd agent installed | none | nothing schedules it |
| `data/logs/` | does not exist | the documented log target was never created |
| Distinct dates in `daily_forward_snapshot` | 5 | Phase 13B screens gate at ≥30 — they have never returned a row |

Two features were designed to earn their value by accruing daily history,
and neither has: the **snapshot-history forward screens** (consensus
rating shift, target price raised) and the **growth-acceleration screen**
(which fills one quarter per ingest because `quarterly_fundamentals`
UPSERTs on MRQ). Both are correct code sitting on an empty table.

Everything in section 4 below is secondary to fixing this.

### Current warehouse

| Measure | Value |
|---|---|
| Active tickers | 507 (1 inactive) |
| Coverage | 100% US / USD, NYSE 343 + NASDAQ 161 + 4 other |
| `prices_daily` | 4,382,337 rows, 1962-01-02 → 2026-05-18 |
| `technicals_daily` | 4,381,692 rows |
| Statements | 81,020 IS / 81,015 BS / 75,133 CF (64,553 quarterly + 16,467 annual) |
| `analyst_estimates_history` | 76,770 rows |
| `earnings_events` | 52,376 rows |
| Warehouse file | 1.2 GB |
| `data/raw/` | 942 MB (508 + 508 JSON files) |
| `data/archive/` | 2.8 GB across 4 dated directories |
| Watchlists | 1 ("Keith's Portfolio", no shares/cost basis populated) |

### Vendor entitlement (checked 2026-08-08)

Paid monthly plan, **daily rate limit 100,000 requests**. The full daily
load of 507 tickers costs ~1,014 requests. **We are using ~1% of what we
pay for.** Every "we can't afford the API calls" assumption in earlier
planning is void.

### Known unimplemented configuration

- `ingest.archive_retention_days: 90` is in `config/settings.yml` and
  **no code reads it**. Nothing purges `data/archive/`. At ~940 MB/day a
  90-day archive is ~85 GB. Also note the archive is a byte copy of
  `data/raw/`, so a 45-year price history is re-copied daily even when a
  single bar changed.

## 2. What shipped

| Phase / ticket | Deliverable | Key files |
|---|---|---|
| 0 | Project setup, deps, lint, test scaffolding | `pyproject.toml`, `tests/test_smoke.py` |
| 1 | Schema + per-section parsers | `migrations/001_initial.sql`, `src/ingest/sections/*.py` |
| 2 | EODHD client + price ingestion | `src/ingest/fetch.py`, `sections/prices.py` |
| 3 | Universe CLI | `src/universe.py`, `scripts/{add_ticker,seed_universe,load_daily}.py` |
| 4 | Computed multiples + TTM views | `src/compute/{ttm,multiples}.py` |
| 5 | MVP Streamlit UI | `src/app/Home.py`, `pages/1_Deep_Dive.py`, `queries.py` |
| 6 | Daily forward snapshot + analyst gauge | `sections/analyst_snapshot.py` |
| 7 | Six trailing screens | `src/screens/trailing.py`, `pages/3_Screens.py` |
| 8 | Sector view + bulk ticker upload | `src/screens/sectors.py`, `pages/5_Sectors.py` |
| 9 | Docker, resumable bulk loader, `load_runs` | `Dockerfile`, `src/ingest/bulk.py`, migration 002 |
| 10 | Watchlists + display/comparison-set discipline | `src/watchlist.py`, `pages/4_Watchlists.py`, migration 003 |
| 11 | Annual statements + period/depth/units toggles | `sections/financials.py`, migration 004 |
| 12 | Universe drill-down modal, paginated prices | `pages/2_Universe.py`, `queries.prices_page` |
| 13A | Vendor-trend forward screens | `src/screens/forward_vendor.py`, migration 005 |
| 13B | Snapshot-history forward screens | `src/screens/forward_history.py`, `pages/6_Forward_Screens.py` |
| INV-1 | Edit watchlist membership | `pages/4_Watchlists.py` |
| INV-2 | Market cap + ADTV filters on screens | `src/compute/size.py` (`universe_size_latest`) |
| INV-3 | Recent-news tab on Deep Dive | `fetch.fetch_news`, `pages/1_Deep_Dive.py` |
| INV-4 | Numeric column sorting via `Styler.format` | `Home.py`, screen pages |
| INV-6 | Threaded "Refresh All" | `orchestrator.refresh_universe_threaded` |
| INV-7 | Technicals: materialized table, 12 screens, Deep Dive chart | migration 007, `src/compute/technicals.py`, `src/screens/technicals.py`, `pages/7_Technical_Screens.py`, `TECHNICALS.md` |

## 3. The ambition

Today the project is a **very good fundamentals browser**. Every number is
correct, every page is fast, and the answer to "what does this company
look like?" is one click away.

What it cannot do is tell you whether any of it works, what you own, or
what changed while you weren't looking. The three-year destination:

> A system that runs itself, records what it believed on every day it ran,
> can prove which of its screens actually predicted returns, knows what
> you hold and why, and tells you each morning what changed.

Four capabilities separate today from that:

1. **It runs unattended and accumulates history.** (W0)
2. **Its history is honestly point-in-time, prices included.** (W1)
3. **It can score its own screens against forward returns.** (W2)
4. **It pushes, not just pulls.** (W4)

Everything else — more data, deeper analytics, nicer tables — is
amplification. These four are the ones that change what the system *is*.

## 4. Workstreams

Ordered by dependency, not by appeal. W0 gates W2 and W4. W1 gates W2.

### W0 — Make it run (prerequisite for everything)

The whole point of the daily cadence is accrual. Until this lands, W2 and
W4 are unbuildable and two shipped screens stay empty.

| # | Increment | Notes |
|---|---|---|
| W0.1 | Backfill the 82-day gap | One `load_daily.py` run. ~1,014 requests against a 100k limit. Restores prices, statements, estimates. Does **not** recreate the 82 missing snapshot dates — those are gone permanently. |
| W0.2 | Install the scheduler | launchd agent (macOS) from the README skeleton. `mkdir -p data/logs` first — the documented log path does not exist. Verify with a forced run, not by reading the plist. |
| W0.3 | Implement archive retention | Wire `ingest.archive_retention_days` to an actual purge in `fetch_and_ingest` or `load_daily`. Currently config theatre; 2.8 GB after 4 days. |
| W0.4 | Stop archiving unchanged price files | Archive fundamentals daily; archive prices only when the file hash changed. Cuts archive growth by roughly 95%. |
| W0.5 | Staleness banner | Home page shows "data as of YYYY-MM-DD (N days stale)" in red past a threshold. This failure was silent for 82 days — make it loud. |
| W0.6 | Load-health page | `load_runs` over time, per-ticker failure streaks, snapshot-coverage sparkline. `queries.snapshot_coverage` already exists and nothing surfaces it. |
| W0.7 | Post-load digest to file | One Markdown file per run in `data/logs/`: N ok / M failed, tickers that failed twice running, new 52w highs/lows. Precursor to W4. |

**Definition of done:** 30 consecutive unattended days, and
`screen_consensus_rating_shift` returns rows.

### W1 — Point-in-time truth on prices

`AGENTS.md` principle #2 claims point-in-time integrity. It holds for
fundamentals (`report_date`, not `fiscal_period_end`) and fails for
prices: `adjusted_close` is overwritten across the whole history on every
load, so a backtest run today sees adjustments that were unknowable then.
No honest backtest is possible until this is fixed.

| # | Increment | Notes |
|---|---|---|
| W1.1 | `corporate_actions` table | Splits + cash dividends with ex-dates. Both already ingested into `splits` / `dividends_declared` — this consolidates and adds the missing ex-date discipline. |
| W1.2 | Adjustment-factor derivation | Cumulative factor from ex-date forward, computed on demand. |
| W1.3 | `price_as_of(ticker, date, as_of)` view | Price adjusted using only actions known by `as_of`. |
| W1.4 | Point-in-time tests | Split-spanning return math must give the same answer whether computed before or after the split. This is the test that proves the workstream. |

### W2 — Backtesting harness (the flagship)

The question the system exists to answer and currently cannot: *do these
screens work?* Point-in-time fundamentals are already in place; W1
supplies the price half.

| # | Increment | Notes |
|---|---|---|
| W2.1 | Screen-replay engine | Run any `src/screens/*` function with an `as_of` date. Requires screens to take `as_of` — a real signature change, worth doing carefully. |
| W2.2 | Forward-return join | For each screen hit, 1/3/6/12-month forward return vs. SPY and vs. sector median. |
| W2.3 | Screen scorecard page | Hit rate, mean/median excess return, decile spread, sample count per screen. |
| W2.4 | Composite backtest | Rank-combine multiple screens; test whether the composite beats its parts. |

**Honest caveat to design around:** the warehouse only holds *current*
vendor statements, so restated figures look like they were always known.
Fundamental replay is therefore approximate for restated periods, and the
scorecard must say so rather than imply precision it doesn't have.

### W3 — Portfolio mode

`watchlist_membership.shares` and `cost_basis` have been nullable-and-
reserved since day one. There is a watchlist literally named "Keith's
Portfolio" with both columns empty. No new schema needed.

| # | Increment |
|---|---|
| W3.1 | Edit shares / cost basis in the Watchlists page |
| W3.2 | Position value, weight, unrealized P&L against `adjusted_close` |
| W3.3 | Sector / size exposure vs. the full universe |
| W3.4 | Contribution to return over a chosen window |
| W3.5 | Portfolio-vs-benchmark chart (SPY from `config/settings.yml:benchmark`) |

### W4 — Push, not pull

507 tickers × 20 screens is more than anyone browses daily. The system
should say what changed.

| # | Increment |
|---|---|
| W4.1 | `events` table: rating change, target-price move >5%, EPS revision, 52w high/low break, golden/death cross, earnings beat/miss |
| W4.2 | Event detection in the daily load, writing to `events` |
| W4.3 | Morning digest — Markdown, scoped to the active watchlist, emitted by the scheduled run |
| W4.4 | Events tab on Deep Dive: what happened to this name, in order |
| W4.5 | Optional email delivery |

### W5 — Data breadth

We use 2 endpoints and ~1% of a 100k/day entitlement. Candidates, in
rough value order:

| # | Increment | Why |
|---|---|---|
| W5.1 | `bulk_fundamentals` endpoint | One request per exchange instead of one per ticker. Could cut the daily load to minutes and make a 3,000-ticker universe practical. |
| W5.2 | Historical market cap | We derive it from `shares_outstanding × price`, which is stale between quarters. Vendor has the series. |
| W5.3 | Index constituents + membership history | Kills survivorship bias in W2. Without it, backtests flatter themselves. |
| W5.4 | Calendars (upcoming earnings, dividends, splits, IPOs) | The "earnings calendar page" backlog item, sourced properly rather than inferred from NULL `eps_actual`. |
| W5.5 | Macro / rates context (Treasury curve, policy rates) | Valuation without a discount-rate anchor is half the picture. |
| W5.6 | Sentiment / news word weights | Feeds W4 event detection. |
| W5.7 | Insider transactions, congressional trades | **Requires a scope decision — see §6.** Currently listed in `AGENTS.md` as explicitly NOT tracked. |

### W6 — Analytics depth

| # | Increment |
|---|---|
| W6.1 | Sector-relative z-scores (value, quality, growth, momentum) |
| W6.2 | Composite factor score per ticker, with per-factor contribution shown |
| W6.3 | Cross-sectional percentile ranks alongside the existing own-history percentiles |
| W6.4 | Peer-set comparison: nearest N names by sector + size, not just sector median |
| W6.5 | Quality-of-earnings flags (accruals, FCF/NI divergence, share-count creep) |

### W7 — UX and performance (carried backlog)

Real, non-urgent, mostly from `REVIEW.md` §4:

- `2_Universe.py` renders ~2,000 buttons at 507 tickers — paginate or move
  actions to a side panel.
- `5_Sectors.py` N+1 query on cold cache — one grouped query.
- `_apply_units` in `1_Deep_Dive.py` hard-codes `$` — use
  `security_master.currency_code`.
- `screen_growth` strict `g1>g2>g3>g4` breaks on one flat quarter — add a
  non-decreasing-with-slack variant.
- `bulk_load.py --resume` should accept a short job-id prefix.
- Compare-two-tickers mode on Deep Dive.
- Per-ticker notes editing on Universe (column exists, no UI).
- Save screen *filters* with a watchlist, not just the resulting tickers.

### W8 — Platform

| # | Increment |
|---|---|
| W8.1 | Read-only Streamlit connection so the UI can't collide with a load |
| W8.2 | Warehouse backup before each load (DuckDB file copy or `EXPORT DATABASE`) |
| W8.3 | Always-on host (EC2 + EBS + systemd timer) — retires the "did the laptop sleep?" failure mode that caused §1 |
| W8.4 | FX activation — loader, USD-equivalent views, native/USD toggle. **Trigger: first non-US ticker.** Not before; the universe is 100% USD today |

## 5. Sequencing

**Next three, in order, nothing else first:**

1. **W0.1** — backfill the gap. One command, restores 82 days.
2. **W0.2 + W0.5** — schedule it, and make staleness visible so silent
   death can't recur.
3. **W0.3 + W0.4** — retention, before the archive becomes a disk problem.

**Then:** W0.6/W0.7 while snapshot history accrues → W1 (independent of
accrual, so it parallelizes with the 30-day wait) → W2 once both are in.

**Opportunistic, any time:** W3 and W7 have no dependencies and are the
best filler work while W0 accrues history.

## 6. Open decisions

Needed before the relevant increment starts:

- **W5.7 scope re-opening.** `AGENTS.md` lists `Holders.*`,
  `InsiderTransactions.*`, short interest, and `ESGScores.*` as
  deliberately out of scope, with a standing instruction to raise it
  before implementing. That decision was made when the only source was the
  big fundamentals JSON; dedicated endpoints and a 100k/day limit change
  the calculus. **Decide explicitly — do not let it drift in via a
  ticket.**
- **W2 restatement honesty.** Accept approximate fundamental replay with a
  documented caveat, or build versioned statement history first? The
  latter is a large schema change. Recommendation: accept the caveat,
  label it prominently in the scorecard.
- **W5.1 universe size.** If bulk fundamentals makes 3,000 tickers cheap,
  do we want them? Larger universe improves comparison-set statistics and
  W2 sample size; it also multiplies warehouse size and load time.
- **W5.3 vs. W2 ordering.** Backtesting without index-membership history
  is survivorship-biased. Ship W2 with a stated bias caveat, or block on
  W5.3? Recommendation: ship with the caveat, prioritize W5.3 right after.

## 7. Decision log

Decisions that should outlive any single ticket.

- **Watchlists are snapshots, not dynamic.** Created from a screen result,
  the ticker list freezes at save time. Re-save to refresh.
- **Comparison set = full active universe** by default. The watchlist
  sidebar filters the display set only. Tests pin the invariant.
- **`add_ticker` writes a pending `active=false` row before ingest.** On
  ingest failure for a brand-new ticker the row is deleted; existing
  tickers keep their row regardless.
- **Universe seed YAML is read only by `seed_universe.py`.** Runtime
  source of truth is the `universe` table.
- **Soft delete only.** Removing a ticker sets `active=false`.
- **`bulk_load.requests_per_minute: 500`** (paid EODHD plan). Tune down
  for the free tier.
- **DuckDB single-writer** is mitigated by a 02:00 load window. W8.1
  (read-only UI connection) is the real fix.
- **Net debt** = `long_term_debt_total + short_term_debt -
  cash_and_short_term_investments`, COALESCE missing components to 0.
- **Beta benchmark** = `config/settings.yml:benchmark.ticker` (`SPY.US`).
- **TTM timing** is unified on `earnings_events.report_date`.
- **Revenue-revision counts are not in EODHD `Earnings.Trend`** — EPS
  revisions only.
- **`eps_trend_30days_ago == 0`** rows are excluded before the % delta.
- **Daily snapshot retention: keep forever.** Revisit at 5 GB.
- **Raw JSON archive: 90 days** (`ingest.archive_retention_days`) —
  **decided but never implemented; see W0.3.**
- **`fetch._get` retry policy**: 4 attempts, exponential backoff from 1 s,
  retries 429 + 5xx + transport errors, no retry on 200-with-Error.
- **`technicals_daily` is a table, not a view** — the documented exception
  to "derive, don't store". Fully regenerable via `recompute_technicals`.
- **EMAs and Wilder's smoothing use `adjust=False`** to match TradingView
  and Bloomberg.
- **(2026-08-08) Unattended operation is a feature, not ops.** Two shipped
  features depend on daily accrual. A scheduler that silently stops is a
  product failure, which is why W0.5 (staleness banner) ships with W0.2
  rather than "later".

## 8. How to use this file

- `AGENTS.md` is the living design doc — update it whenever a ticket
  changes a convention.
- This file holds the workstreams, the shipped inventory, and the decision
  log. Jira holds individual tickets.
- `REVIEW.md` is a May-2026 snapshot; replace it after W2 lands.
- Re-baseline this file whenever the gap between "what shipped" and
  "what's here" gets uncomfortable — it drifted twice already.
