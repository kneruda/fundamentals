# Ticket: Technicals indicators, screens, and Deep Dive panel

## Summary

Replace the existing `technicals_daily` view with a materialized table of the
same name, expand its indicator coverage (RSI, MACD, Bollinger Bands, ATR,
EMAs, distance and position metrics), expose those indicators via a new
"Technicals" screen group, and add a Technicals panel to the Deep Dive page
with interactive Plotly charts.

This is a standalone ticket — does not modify PLAN.md or introduce a new
phase.

## Background

The existing `technicals_daily` view (built by `src/compute/technicals.py`
as `CREATE OR REPLACE VIEW`, wired via
`schema/runner.py::open_db() → compute.setup_views()`) holds SMA 20/50/200,
52w high/low, realized volatility, and beta. It is correct and tested
(Phase 4 tests) but no page or screen in the app currently reads from it —
it is effectively dead code.

Two reasons to consolidate rather than layer on top:

- Several new indicators (EMA, Wilder's RSI, MACD, ATR) require
  recursive / EWM computation that is awkward in pure SQL. Materializing in
  pandas is the cleanest path.
- A view (existing technicals) + a table (new indicators) joined on
  `(ticker, date)` is incidental complexity given the view is not surfaced
  anywhere.

The "derive don't store" principle in AGENTS.md targets stored values that
can silently disagree with their inputs. The new table is fully regenerable
from `prices_daily` via a single deterministic function and is never written
by anything else — the principle is not violated.

Out of scope per AGENTS.md: vendor `Technicals.*` block. We derive
everything ourselves.

## Materialization change

- Migration `src/schema/migrations/00X_technicals_daily_table.sql` (next
  available numeric prefix):
  `DROP VIEW IF EXISTS technicals_daily; CREATE TABLE technicals_daily (...);`.
  Include all columns listed in the next section.
- `src/compute/technicals.py` rewritten: replace the view-builder with
  `recompute_technicals(con, tickers=None)`. `tickers=None` means full
  active universe. Reads `prices_daily` into pandas per ticker, computes
  indicators (`ewm(adjust=False)` for EMAs; Wilder's smoother for RSI and
  ATR), and bulk-inserts into `technicals_daily`. Deletes existing rows for
  each ticker before inserting so the function is idempotent.
- `schema/runner.py::open_db()` keeps calling `compute.setup_views()` for
  the remaining views (`ttm_*`, `trailing_multiples_daily`), but the
  technicals call is removed from `setup_views()`. Technicals is now a
  recompute, not a view.
- Wire `recompute_technicals(con, [ticker])` into
  `src/ingest/orchestrator.py` after a successful price ingest for that
  ticker. Per-ticker history is well under 10k rows; cost is negligible.
- Wire `recompute_technicals(con)` into `scripts/rebuild.py` after the bulk
  reload.

The existing Phase 4 tests stay in place. Every column they check
(`sma_20`, `sma_50`, `sma_200`, `beta_252d`, `realized_vol_60d`,
`high_52w`, `low_52w`) exists in the new table with the same definitions.
The fixtures need light edits to call `recompute_technicals()` after
seeding `prices_daily` rather than relying on view-creation-at-connect.

## Columns in `technicals_daily`

Grain `(ticker, date)`. All indicators computed from `adjusted_close` (and
`volume` where relevant). Fixed conventional parameters at this layer;
adjustable parameters are deferred to a future ticket.

Existing (preserved from the view definition):

- `sma_20`, `sma_50`, `sma_200`
- `high_52w`, `low_52w`
- `realized_vol_60d`
- `beta_252d`

New trend / moving averages:

- `ema_12`, `ema_26`, `ema_50`
- `pct_from_sma_50`, `pct_from_sma_200` = `(adjusted_close − sma) / sma`

New momentum:

- `rsi_14` — Wilder's RSI
- `macd` = `ema_12 − ema_26`
- `macd_signal` — 9-period EMA of `macd`
- `macd_histogram` = `macd − macd_signal`

New volatility / range:

- `bb_middle` (= `sma_20`), `bb_upper`, `bb_lower` — 20-period, 2σ
- `bb_width` = `(bb_upper − bb_lower) / bb_middle`
- `atr_14` — Wilder's ATR

New volume:

- `volume_sma_50`
- `volume_ratio` = `volume / volume_sma_50`

New 52-week position:

- `pct_from_52w_high` (≤ 0)
- `pct_from_52w_low` (≥ 0)

## Screens

New module `src/screens/technicals.py`. Each function returns a DataFrame
scoped to the active universe with the columns that drove the filter, so
the UI can display *why* a match qualified. Thin wrappers in
`src/app/queries.py`. The Screens page gets a "Technicals" group using the
existing selector / parameter pattern.

Trend:

- `screen_confirmed_uptrend` — price > SMA200 AND SMA50 > SMA200
- `screen_confirmed_downtrend` — price < SMA200 AND SMA50 < SMA200
- `screen_golden_cross_recent` — SMA50 crossed above SMA200 within the last
  N days (default 30)
- `screen_death_cross_recent` — symmetric

Momentum:

- `screen_rsi_oversold` — RSI14 < threshold (default 30)
- `screen_rsi_overbought` — RSI14 > threshold (default 70)
- `screen_macd_bullish_crossover` — MACD crossed above signal within last N
  days (default 5)
- `screen_macd_bearish_crossover` — symmetric

Position:

- `screen_near_52w_high` — price within X% of 52w high (default 5%)
- `screen_near_52w_low` — price within X% of 52w low (default 5%)

Volatility / volume:

- `screen_bb_squeeze` — BB width below own 252-day Nth percentile
  (default 20th)
- `screen_volume_spike` — `volume_ratio` > threshold (default 2.0)

## Deep Dive panel

Add a "Technicals" panel to `src/app/pages/1_Deep_Dive.py` after the
existing panels. Plotly for interactivity. Time range selector:
6M / 1Y / 3Y / 5Y / Max, default 1Y.

Layout — stacked subplots sharing x-axis:

1. Price (≈50% height) — adjusted close line (default) or candlestick
   (toggle). SMA20, SMA50, SMA200 overlays. Bollinger Bands overlay,
   toggleable, off by default.
2. Volume (≈15%) — bars colored green/red by day's direction;
   `volume_sma_50` line overlay.
3. RSI (≈17%) — line with 30/70 reference lines and shaded oversold /
   overbought zones.
4. MACD (≈18%) — MACD line, signal line, histogram bars.

Above the chart, a compact "current signals" table with the latest values
for RSI, MACD histogram sign, BB position (lower / middle / upper third),
`pct_from_sma_200`, `pct_from_52w_high`, `volume_ratio`. Each row
color-coded green / red / neutral.

All chart series read through `queries.deep_dive_technicals(ticker,
lookback)`. No raw SQL in the page.

## Tests

In `tests/`:

- Keep the existing Phase 4 tests for SMA / beta / realized volatility /
  52w high-low. Adapt fixtures to call `recompute_technicals()` after
  seeding `prices_daily` rather than relying on view-creation-at-connect.
- New unit test per indicator using a hand-constructed price fixture with
  known output. Wilder's RSI has a canonical example sequence in standard
  references; use it for `rsi_14`. Use comparable canonical inputs for ATR
  and EMA.
- `test_recompute_idempotent` — `recompute_technicals(con, [ticker])` twice
  in a row produces identical rows.
- `test_recompute_full_rebuild` — wiping `technicals_daily` and recomputing
  matches running on top of populated rows.
- Per-screen smoke test on the MVP universe fixture: each screen runs
  without error and returns a DataFrame with the expected columns.
- Edge cases:
  - Ticker with < 200 days of history: SMA200, RSI, BB, ATR return NULL,
    no error.
  - Ticker with zero or null `volume` (e.g., a synthetic index): volume
    indicators NULL.
  - Single-day history: all indicators NULL.

## Acceptance criteria

- `uv run python scripts/rebuild.py` populates `technicals_daily` for every
  active ticker with no errors.
- `uv run python scripts/add_ticker.py <NEW>` populates technicals for the
  new ticker end-to-end.
- The Screens page exposes a "Technicals" group; each listed screen runs
  against the MVP universe and returns results.
- The Deep Dive page renders the four-pane technicals chart with all
  overlays / toggles functional, plus the current-signals summary.
- `uv run pytest` is green, including the new tests and the adapted Phase
  4 tests.
- `uv run ruff check . && uv run black --check .` is clean.
- AGENTS.md updated:
  - Data model summary table: `technicals_daily` line updated from
    "derived / view" to "table, recomputed from `prices_daily`".
  - The "Derived (materialized views or computed at query time, never
    persisted)" paragraph adjusted to acknowledge `technicals_daily` as
    the documented exception, with rationale.
  - The Phase 4 "Beta benchmark ticker from settings" note carried
    forward into the new compute module (still reads `benchmark.ticker`
    from `settings.yml`).
  - The Phase 4 "Derived views live in Python, not in migrations" note
    updated to reflect that `technicals_daily` is now a table created by
    migration; other views remain code-defined.
  - Any new anti-patterns discovered (likely candidates: EWM warm-up
    gotchas, NULL handling in cross-detection windows over short
    histories).

## Out of scope / future

- Adjustable indicator parameters (custom SMA period, RSI(7),
  MACD(8,17,9), etc.). Two natural paths when this is picked up: live
  recompute in the Deep Dive query function for chart overlays (cheap,
  single ticker), and either more materialized columns or accepting
  universe-scan cost for screens.
- Pattern recognition (head-and-shoulders, flags, etc.).
- Multi-indicator composite screens (e.g., "oversold AND in confirmed
  uptrend"). Compose by running screens sequentially for now.
- Indicator-threshold alerts (would need accumulated indicator-state
  history, deferred).
- Backtesting harness.

## Design questions — confirm before implementation

1. **Source price column.** `adjusted_close` throughout, including ATR
   (conventionally raw H/L/C). Rationale: long-history continuity across
   splits beats "true" ATR around split events. Confirm or override.
2. **EMA warm-up.** pandas `ewm(adjust=False)` (recursive seed = first
   value) matches TradingView and most charting platforms. Confirm or
   override to `adjust=True`.
