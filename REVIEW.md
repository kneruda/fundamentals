# REVIEW.md

A thorough code review of the fundamentals dashboard at the close of the
phased build-out. Snapshot: 507 tickers loaded, 330 MB warehouse, 221 tests
all passing in ~19 s.

## 0. Status of recommendations (post-review cleanup)

The cleanup pass below addressed every Section 8 recommendation plus the
quick wins from Section 4. All 221 tests still pass after the changes.

| Item | Status | Notes |
|---|---|---|
| 3.1 `scripts/rebuild.py` missing | Fixed | New script ingests local raw JSON without re-fetching. `--tickers` and `--skip-prices` flags. |
| 3.2 Doc drift (schema, migration numbers) | Fixed | `AGENTS.md`, `PLAN.md`, and `README.md` rewritten in same commit. |
| 3.3 RPM default mismatch | Fixed | Docs aligned to `bulk_load.requests_per_minute: 500` in `config/settings.yml`. |
| 3.4 Daily load summary | Fixed | `load_daily.py` now logs `N ok / M failed in <duration>` and per-ticker failures. |
| 3.5 `load_runs` no PK | Fixed | Migration `006_load_runs_pk.sql` adds `PRIMARY KEY (ticker, run_started_at)`. |
| 3.6 Silent USD currency fallback | Fixed | `general.py` and `financials.py` now raise on missing `General.CurrencyCode`. |
| 3.7 Raw SQL interpolation in forward_history | Fixed | Both screens use parameterized `?` placeholders. |
| 3.10 Unused `vcrpy` dev dep | Fixed | Removed from `pyproject.toml`. |
| 4 – `Home.py` duplicated format map | Fixed | Pulled into module-level constants `_COLUMN_FORMATS` / `_COLUMN_LABELS`. |
| 4 – `fetch._get` final error context | Fixed | Includes `last_status` and `last_error` in the raised message. |
| 4 – `ingest_universe` failure count | Fixed | Returns `list[(ticker, ok, msg)]`; caller surfaces a summary. |
| 3.8 `next_period_end` vendor dependency | Documented | No code change; flagged as known limitation. |
| 3.9 Growth history fills over time | Documented | Acknowledged in PLAN.md backlog and AGENTS.md "Known limitations". |
| 3.11 `is` SQL alias | Verified clean | No action. |
| 4 – Sectors N+1, Universe button rerender, units `$` hard-code, growth strict ordering, bulk_load short job-id, watchlist race | Deferred to Jira | Real but non-urgent; itemized in PLAN.md backlog. |

## 1. Summary

The project landed all 13 phases cleanly. The architectural backbone —
cadence-aware storage, point-in-time integrity via `report_date`, UPSERT
idempotency, derived-views-as-code, display-vs-comparison-set discipline,
single shared ticker-input parser — is intact across the codebase. Every
module of consequence has tests, and the tests are tight enough to catch
real regressions (period_type discriminator, FCF-conversion sign handling,
watchlist comparison-set invariance, etc.).

The system is **ready for Jira-driven incremental work**. Before opening
that next chapter there are a small number of cleanups, doc/schema drift
items, and latent footguns worth addressing. Most are 15-30 minute fixes.

**Risk grade**: low for personal use. Medium-low if extending to multiple
users or non-US tickers.

## 2. What's good

- **Idempotent ingestion, end to end.** Every UPSERT table has a natural
  PK; every parser writes through `_util.upsert_df`; `test_idempotency`
  re-runs ingest and asserts byte-stable row counts.
- **Point-in-time joins use `report_date` consistently.** The TTM views
  (`ttm_eps`, `ttm_revenue`, `ttm_ebitda`, `ttm_fcf`) all source
  `report_date` from `earnings_events`, preventing the original cross-view
  timing drift mentioned in PLAN.md.
- **`config/settings.yml` centralizes everything tunable.** Paths,
  benchmark ticker, vendor RPS, bulk-load RPM, archive retention. Nothing
  worth tuning is hard-coded.
- **Single ticker-input parser.** Bulk universe upload (`2_Universe.py`)
  and watchlist creation (`4_Watchlists.py`) both call
  `parse_ticker_input`. `test_parse_ticker_input_same_as_parse_tickers`
  pins the equivalence.
- **`queries.py` is the only data-access layer page files touch.** Pages
  are presentation; SQL is in `queries.py`, `src/screens/`, or
  `src/compute/`. The discipline holds across all six pages.
- **Test coverage is broad and fixture-based.** 221 tests, one phase per
  file, AAPL fundamentals + price JSON as the canonical fixture. Phase 4
  (computed multiples) and Phase 7 (screens) use synthetic helpers
  (`insert_earnings`, `insert_prices`, …) for edge cases like
  loss-makers, restatements, and short history.
- **Docker is minimal and works.** `python:3.11-slim` + `uv` + the repo;
  two compose services share the same image. `make load`, `make ui`,
  `make shell`, `make test` are all one-liners.
- **Display-set / comparison-set discipline is enforced.** Trailing
  screens accept `display_filter`; `sector_summary` does not, and
  `sector_constituents` accepts it for the drill-down only. Phase 10
  tests assert that medians stay anchored to the full universe.

## 3. Issues to fix (high → low priority)

### 3.1 Missing referenced script: `scripts/rebuild.py`

Mentioned 4 times in docs (AGENTS.md `repository layout`, AGENTS.md `Build /
test commands`, README "Other scripts", README "Dev commands") but does
not exist. Either:

- delete the references, or
- add a thin `rebuild.py` that opens the warehouse and calls
  `ingest_ticker` on each `data/raw/fundamentals/*.json` (paired with the
  matching `data/raw/prices/*.json`) — useful for schema migrations that
  need a re-ingest without re-fetching from EODHD.

The second is small (~30 lines) and would have saved time the last time
a migration touched the statement tables. Recommendation: write it.

### 3.2 Doc drift between AGENTS.md and the actual schema

| Doc says | Schema actually has |
|---|---|
| `bulk_load_jobs` columns include `started_at`, `finished_at` | `created_at`, `updated_at` |
| `load_runs` `PRIMARY KEY (ticker, run_started_at)` | no PRIMARY KEY |
| `002_statements_period_type.sql` | actual file is `004_statements_period_type.sql` |
| `005_analyst_estimates_trend_cols.sql` | (matches) |
| migration ordering implies a 005 migration covers Phase 13 trends | does, but PLAN.md is out of sync on file numbering |

Fix during the AGENTS.md/PLAN.md rewrite below.

### 3.3 `bulk_load.requests_per_minute: 500` ≠ documented default

`config/settings.yml` ships **500 RPM**. README says "Default throttle: 20
tickers/min". AGENTS.md and PLAN.md describe a "conservative 20 RPM"
default. The 500-RPM value was clearly tuned up after the first successful
500-ticker bulk load, but the docs never followed. Pick one and align.
Recommendation: bump the docs to match what's actually checked in, with a
one-line "tune for your EODHD plan" caveat.

### 3.4 Daily load is unbatched and unthrottled at the ticker level

`scripts/load_daily.py` → `ingest_universe()` → for-loop calling
`fetch_and_ingest()` per ticker. The only pacing is `time.sleep(1.0/rps)`
inside `fetch._get` (currently 10 RPS → 100 ms per HTTP call). With 2
calls per ticker that's a floor of ~200 ms per ticker, or ~100 s for 500
tickers — best case. There is **no resume**: if it crashes at ticker 400,
the next run starts from ticker 1 (idempotent reload, but ~30 s wasted).

Three small improvements:

1. Have `load_daily.py` use the same `bulk_load_jobs` checkpoint table the
   bulk loader uses — instant resume on crash.
2. Or: write per-ticker `load_runs` rows as it goes (already does) and use
   them to skip tickers whose last load was today and `status='ok'`.
3. Surface a final summary line: "507 ok / 0 failed in 14m 22s".

Low priority unless the daily load actually fails enough to matter.

### 3.5 `load_runs` has no PRIMARY KEY

```sql
CREATE TABLE IF NOT EXISTS load_runs (
    ticker          VARCHAR NOT NULL,
    run_started_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ...
);
```

Re-running ingest on the same ticker within the same second would (in
theory) create duplicate rows. Unlikely in normal operation but trivially
fixed by adding `PRIMARY KEY (ticker, run_started_at)` in a new migration,
or by tolerating it (the table is monitoring-only — no downstream
consumer cares about uniqueness).

### 3.6 Currency fallback to `'USD'` is silent

`src/ingest/sections/general.py:52` and `financials.py:32`:

```python
"currency": data.get("General", {}).get("CurrencyCode", "USD"),
```

For non-US tickers (Phase 14), if `General.CurrencyCode` is missing the
fallback assumes USD silently. That's a bug-in-waiting that disappears the
day the first non-US ticker arrives. Two options:

1. Raise on missing currency: fail the section, the rest of the ticker
   still loads. The section's row never reaches the warehouse with the
   wrong currency.
2. Log a warning and fall back. Less safe but won't break ingestion in a
   way that's hard to debug.

Recommendation: (1). The reporting layer can't recover from a wrong
currency once it's persisted.

### 3.7 Raw SQL string interpolation in `forward_history.py`

```python
tickers_sql = ", ".join(f"'{t}'" for t in eligible)
df = con.execute(f"... WHERE ticker IN ({tickers_sql}) ...")
```

Used in both `screen_consensus_rating_shift` and `screen_target_price_raised`.
Not an injection risk in practice — tickers come from the warehouse — but
it's the one place the codebase abandons parameterized queries. DuckDB
1.1+ supports `WHERE ticker = ANY(?)` with a Python list parameter; switch
to that for consistency.

### 3.8 `next_period_end` relies on EODHD pre-populating future rows

`queries.ticker_header` (Deep Dive header) computes:

```sql
SELECT MIN(fiscal_period_end) FROM earnings_events
WHERE ticker = ? AND eps_actual IS NULL AND fiscal_period_end > CURRENT_DATE
```

If the vendor stops pre-populating the next-quarter row (it currently
does), the header silently shows "—". Worth knowing if it ever stops
working.

### 3.9 Highlights drives historical growth screens via UPSERT

`screen_growth` (and the q1/q2/q3/q4 acceleration check) read
`quarterly_fundamentals` for `quarterly_revenue_growth_yoy` historical
values. Because `quarterly_fundamentals` is UPSERTed on `(ticker,
mrq_period_end)`, the only way we accumulate per-quarter history is by
running daily and capturing each new MRQ as it rolls forward. A ticker
added today only has the latest quarter's value; quarters Q-1..Q-4 will
fill in over the next 12 months. Not a bug, but worth flagging in the
"Known limitations" section because it explains the empty cells on the
growth-acceleration screen for newly-added tickers.

### 3.10 Pyproject deps: `vcrpy` listed but unused

`pyproject.toml` includes `vcrpy>=6.0` in the dev group; AGENTS.md notes
that vendor client tests use mocks not VCR. Either drop the dep or
introduce a recorded-cassette test against a real EODHD response. The
latter is genuinely useful (mocks lie). Low priority.

### 3.11 `is` as SQL alias — actually fine, but check Phase 12 ingestion

AGENTS.md explicitly forbids `is` as a SQL alias. A quick scan confirms
the codebase uses `i`/`bs`/`is`/`ee`/etc. but never just `is` as an
alias. Verified clean. (Mentioned only because the anti-pattern is in the
docs.)

## 4. Small footguns and code smells

- **`Home.py` duplicates the format/gradient map.** The dict literal
  `{"price": "${:.2f}", ...}` appears twice (in `_style_table` and again
  inline in `main`). Pull into a module-level constant.
- **`5_Sectors.py` calls `_sector_constituents` inside a per-sector loop.**
  Each call is cached via `@st.cache_data`, so on a warm cache this is
  fine, but the cold path runs N+1 queries. Consider a single query that
  returns all constituents grouped by sector and split in Python.
- **`2_Universe.py` per-ticker action buttons (Remove, Refresh, Drill).**
  Rendered in a for-loop with one row per ticker. At 500 tickers that's
  2,000 buttons rendered every Streamlit rerun. Works but is sluggish.
  Consider paginating the active-tickers list, or switching to a
  selectbox + action panel.
- **`_apply_units` in `1_Deep_Dive.py`.** Currency-aware formatting
  hard-codes `$`. For non-US tickers the prefix should be the ticker's
  reporting currency from `security_master.currency_code`.
- **`screen_growth` percent acceleration logic** uses
  `g1 > g2 AND g2 > g3 AND g3 > g4` strict ordering — one flat quarter
  breaks the chain. Fine as written but worth knowing.
- **`fetch._get` retry logic.** Per-attempt sleep is exponential, but on
  the final attempt it raises `RuntimeError("All N attempts failed")`. No
  context (URL, last status code) in the message. Trivial to improve.
- **`ingest_universe` per-ticker exception handler** logs but doesn't
  count. Final summary would be one line of code.
- **`bulk_load.py` `--resume` is documented but the job_id is a UUID.**
  Users will copy-paste from log output; consider also accepting a short
  prefix.
- **`watchlist._next_id`** uses `COALESCE(MAX(watchlist_id), 0) + 1`. Safe
  for single-writer DuckDB but a race on a hypothetical second writer.
  Not a real risk today.
- **`screen_relative_history`** computes `PERCENT_RANK()` in SQL — DuckDB
  supports this. The AGENTS.md anti-pattern warning is about
  `PERCENT_RANK() WITHIN GROUP`, which is the variant we *don't* use.
  Worth tightening the doc.

## 5. Architecture / design observations (not bugs)

- **Statement tables are 64/34/32 columns wide**, normalized straight from
  EODHD. The "Summary vs Full" toggle in the UI handles the
  human-readability question without compromising warehouse fidelity.
  This design has worked well; keep it.
- **`adjusted_close` overwrite-on-load semantics are correct.** Verified
  against the AAPL split (`2020-08-31` close 499.23 vs adjusted 121.17).
  The "no point-in-time `adjusted_close`" trade-off is documented and
  appropriate for the current use case.
- **`daily_forward_snapshot` is the only growing-by-day table.** At one
  row per ticker per day, 500 tickers × 365 days = ~180k rows/year. The
  table will stay small for years.
- **The `period_type` discriminator on statement tables works.** All
  `queries.*` helpers filter on it; the `quarterly_metrics` test pins
  the no-double-count invariant.
- **Phase 13A vendor-trend screens work immediately on new tickers.**
  Phase 13B snapshot-history screens correctly gate on `n_days >=
  min_history_days`. Both UI banners surface excluded counts.
- **Forward EPS estimates** (`eps_estimate_curr_y` etc.) come from the
  `Highlights` block, snapshotted into `daily_forward_snapshot` daily.
  This is the right cadence and the right place.

## 6. What's intentionally NOT in this review

Per AGENTS.md "Out of scope — DO NOT IMPLEMENT": holders, insider
transactions, technicals (we derive our own), short interest, ESG,
addresses beyond country/currency, cross-listings. The schema and parsers
correctly omit all of these.

## 7. Specific files / lines worth re-reading

- `src/compute/ttm.py` — the one place where TTM timing semantics live.
  Worth re-reading whenever a screen returns surprising values around
  earnings windows.
- `src/ingest/orchestrator.py:_fresh_today` — the "fetched today, skip
  re-fetch" guard. Subtle: it uses local-time `date.today()`, so a
  midnight-UTC cron job on a US-east machine looks "stale" until the next
  morning. Hasn't bitten yet; flag for the day it does.
- `src/schema/migrations/004_statements_period_type.sql` — the only
  destructive-shape migration. Sets the pattern for any future
  statement-table change. Re-read before touching `income_statement`,
  `balance_sheet`, or `cash_flow`.
- `src/screens/trailing.py:screen_quality` — the most complex screen by
  CTE count (6). Functions correctly; will be the first to break if a
  statement column is renamed.

## 8. Recommendations going into the Jira phase

1. **Fix the doc drift** (rebuild.py, bulk_load_jobs columns, load_runs
   PK, RPM defaults). Half a day max. Aligned docs prevent the next
   contributor (or future-you) from spending half a day reverse-engineering
   the current state.
2. **Add a `rebuild.py`** for the next migration that needs a re-ingest
   without re-fetching. Specifically useful when adding new columns to
   `analyst_estimates_history`, statement tables, etc.
3. **Defang the currency-fallback bug** before the first non-US ticker
   lands. Replace `data.get("...", "USD")` with an explicit raise.
4. **Add a final summary line to `load_daily.py`** so the cron log says
   `507 ok / 0 failed in 14m 22s` instead of trailing off.
5. **Re-baseline `AGENTS.md`, `PLAN.md`, `README.md`** to reflect the
   current state and the Jira-driven future. (This commit covers it.)

After those: the system is in good shape for incremental feature work.
