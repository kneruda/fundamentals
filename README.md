# Fundamentals Dashboard

Personal equity fundamentals dashboard powered by [EODHD](https://eodhd.com/).
Tracks valuation, profitability, growth, balance-sheet strength, technicals,
and analyst expectations for a user-managed universe of stocks.

Currently loaded: **507 US tickers**, price history back to 1962, quarterly
and annual statements, daily analyst snapshots.

| Doc | What it is |
|---|---|
| **`AGENTS.md`** | Living design document — principles, conventions, anti-patterns. Read first. |
| **`PLAN.md`** | Current status, workstreams, decision log. |
| **`CODE_TUTORIAL.md`** | Guided tour of the codebase for a new reader. |
| **`TECHNICALS.md`** | Indicator definitions and the technicals build spec. |
| **`REVIEW.md`** | Point-in-time code review (May 2026). |

## Quickstart

```bash
uv sync                                      # install deps
cp .env.example .env                         # then set EODHD_API_TOKEN
uv run python scripts/seed_universe.py       # seed ~10 tickers
uv run streamlit run src/app/Home.py         # UI on :8501
```

Use the **Universe** page to add, remove, and bulk-load tickers.

## Daily operation

**This matters more than it looks.** Two features — the snapshot-history
forward screens and the growth-acceleration screen — only produce signal
after ~30 days of consecutive daily loads. A loader that quietly stops
takes those features with it.

```bash
mkdir -p data/logs
uv run python scripts/load_daily.py          # refresh all active tickers
```

A full 507-ticker load costs ~1,014 API requests. Check your headroom with
your EODHD account's daily rate limit before scaling the universe.

### Scheduling

Run once per day after US market close. The default 02:00 window avoids
colliding with an open Streamlit session (DuckDB allows one writer).

**Cron** — see [`scripts/cron.example`](scripts/cron.example):

```
0 2 * * 1-5 cd /path/to/fundamentals && uv run python scripts/load_daily.py \
    >> data/logs/cron.log 2>&1
```

**macOS launchd** — `~/Library/LaunchAgents/com.fundamentals.load_daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>             <string>com.fundamentals.load_daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/uv</string>
        <string>run</string>
        <string>python</string>
        <string>/path/to/fundamentals/scripts/load_daily.py</string>
    </array>
    <key>WorkingDirectory</key>  <string>/path/to/fundamentals</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>   <integer>2</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>   <string>/path/to/fundamentals/data/logs/load_daily.log</string>
    <key>StandardErrorPath</key> <string>/path/to/fundamentals/data/logs/load_daily.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.fundamentals.load_daily.plist
```

Verify it actually ran — don't assume. `SELECT MAX(date) FROM prices_daily`
should track the last trading day, and `load_runs` should gain a row per
ticker per run.

## Pages

- **Home** — universe summary with conditional formatting.
- **Deep Dive** — one ticker across eight tabs: valuation history,
  profitability, analyst snapshot, earnings, dividends, statements
  (quarterly/annual, summary/full, B/M/K/raw units), recent news, and
  technicals with interactive charts.
- **Universe** — add / remove / refresh / bulk-add; per-ticker load status;
  drill-down modal with paginated prices; threaded "Refresh All".
- **Screens** — six trailing screens (absolute valuation, relative to own
  history, growth, quality, balance sheet, income), with market-cap and
  average-daily-trading-value filters.
- **Watchlists** — named subsets; membership is editable. The active
  watchlist scopes what you see; medians and percentiles stay anchored to
  the full universe.
- **Sectors** — median trailing metrics per GIC sector, with constituents.
- **Forward Screens** — vendor-trend screens (EPS revised up, net upward
  revisions, beat-and-raise) plus snapshot-history screens (consensus
  rating shift, target price raised — needs ≥30 days of daily loads).
- **Technical Screens** — 12 screens over `technicals_daily`: confirmed
  up/downtrend, golden/death cross, RSI oversold/overbought, MACD
  crossovers, near 52w high/low, Bollinger squeeze, volume spike.

## Bulk loading

```bash
# tickers.txt: one per line; # comments and blank lines ignored
uv run python scripts/bulk_load.py --file tickers.txt
uv run python scripts/bulk_load.py --resume <job_id>     # after an interruption
```

Throttles live in `config/settings.yml` under `bulk_load`. Each ticker
costs 2 API calls (fundamentals + prices).

## Scripts

```bash
uv run python scripts/add_ticker.py SHOP     # add one ticker
uv run python scripts/load_daily.py          # daily refresh, all active tickers
uv run python scripts/seed_universe.py       # (re-)seed from config/universe.yml
uv run python scripts/rebuild.py             # re-ingest local raw JSON, no re-fetch
```

`rebuild.py` is the tool for schema migrations that need a re-ingest —
it reads `data/raw/` instead of hitting the vendor. `--tickers` and
`--skip-prices` narrow the run.

## Docker

```bash
docker compose build
docker compose run --rm app uv run python scripts/load_daily.py
docker compose up streamlit                  # UI on :8501
```

Or `make load`, `make ui`, `make shell`, `make test`. Both workflows mount
`./data` and `./.env` into the container.

## Dev

```bash
uv run pytest                                # 253 tests, ~24s
uv run ruff check . && uv run black --check .
```

## Configuration

- **Secrets** — `.env` (never committed). Copy from `.env.example`.
- **Settings** — `config/settings.yml`: paths, vendor throttles, benchmark
  ticker, archive retention.
- **Seed universe** — `config/universe.yml`. Read only by
  `seed_universe.py`; the runtime source of truth is the `universe` table.

## Storage

`data/` grows faster than you'd expect:

| Path | Contents | Size today |
|---|---|---|
| `data/warehouse.duckdb` | the database | 1.2 GB |
| `data/raw/` | latest JSON per ticker, overwritten daily | 942 MB |
| `data/archive/` | dated copies for audit | 2.8 GB, ~940 MB per load |

`ingest.archive_retention_days` is set to 90 but **no code enforces it
yet** — purge `data/archive/` manually, or set
`ingest.archive_raw_files: false`, until that ships (PLAN.md W0.3).

## Vendor

[EODHD](https://eodhd.com/). Two endpoints drive ingestion —
`/api/fundamentals/<ticker>` and `/api/eod/<ticker>` — plus `/api/news`
for the Deep Dive news tab. Shipped throttles assume a paid plan; tune
`config/settings.yml` to yours.
