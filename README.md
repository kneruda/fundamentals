# Fundamentals Dashboard

Personal equity fundamentals dashboard powered by [EODHD](https://eodhd.com/).
Tracks valuation, profitability, growth, balance-sheet strength, and
analyst expectations for a user-managed universe of stocks.

- **`AGENTS.md`** — design guidance, conventions, anti-patterns.
- **`PLAN.md`** — what shipped, backlog, decision log.
- **`REVIEW.md`** — end-of-build code review.

## Quickstart

```bash
# 1. Install deps
uv sync

# 2. Configure your EODHD API token
cp .env.example .env
# Edit .env and set EODHD_API_TOKEN=<your_token>

# 3. Seed the warehouse with the initial universe (~10 tickers)
uv run python scripts/seed_universe.py

# 4. Launch the dashboard
uv run streamlit run src/app/Home.py
```

The dashboard opens at <http://localhost:8501>. Use the **Universe** page
to add/remove tickers, view load status, and run bulk uploads from there.

## Docker

```bash
docker compose build
docker compose run --rm app uv run python scripts/seed_universe.py
docker compose run --rm app uv run python scripts/load_daily.py
docker compose up streamlit          # UI on :8501
```

Or via Makefile: `make load`, `make ui`, `make shell`, `make test`. Both
workflows mount `./data` and `./.env` into the container so the
warehouse and API token are shared.

## Pages

- **Home** — universe summary with conditional formatting.
- **Deep Dive** — single-ticker valuation history, profitability,
  analyst snapshot, earnings, dividends, and statements (quarterly /
  annual; summary / full; B / M / K / raw units).
- **Universe** — add / remove / refresh / bulk-add tickers; per-ticker
  load status and price-range; drill-down modal with paginated prices.
- **Screens** — six trailing screens (absolute valuation, relative to
  own history, growth, quality, balance sheet, income).
- **Watchlists** — named subsets of the universe. Active watchlist scopes
  display across pages; medians/percentiles stay anchored to the full
  universe.
- **Sectors** — median trailing metrics per GIC sector with constituent
  drill-down.
- **Forward Screens** — vendor-trend screens (EPS revised up, net upward
  revisions, beat-and-raise) plus snapshot-history screens (consensus
  rating shift, target price raised; requires ≥30 days of accumulated
  snapshots).

## Bulk-loading a large universe

```bash
# tickers.txt: one ticker per line; # comments and blank lines ignored
uv run python scripts/bulk_load.py --file tickers.txt

# If the job is interrupted, resume with the printed job ID
uv run python scripts/bulk_load.py --resume <job_id>
```

Throttling is configurable in `config/settings.yml` under `bulk_load`.
The shipped value is tuned for our EODHD plan — adjust for yours. Each
ticker makes 2 API calls (fundamentals + prices) and one call to the
warehouse.

## Other scripts

```bash
uv run python scripts/add_ticker.py SHOP      # add one ticker
uv run python scripts/load_daily.py           # daily refresh (all active tickers)
uv run python scripts/seed_universe.py        # (re-)seed from config/universe.yml
```

## Scheduling the daily load

Run `scripts/load_daily.py` once per day after US market close.
Forward-looking history screens accumulate signal after ~30 days of
daily snapshots per ticker.

> **DuckDB constraint**: one writer at a time. Schedule loads during
> quiet hours (default cron is 02:00 local) so they don't conflict with
> an open Streamlit session.

### Cron (macOS / Linux)

See [`scripts/cron.example`](scripts/cron.example). Quick setup:

```bash
mkdir -p data/logs
crontab -e
```

Add (runs at 02:00 local, Mon–Fri via Docker):

```
0 2 * * 1-5 cd /path/to/project && docker compose run --rm app \
    uv run python scripts/load_daily.py >> data/logs/cron.log 2>&1
```

Or without Docker:

```
0 2 * * 1-5 cd /path/to/project && uv run python scripts/load_daily.py \
    >> data/logs/cron.log 2>&1
```

### macOS launchd

A `~/Library/LaunchAgents/com.fundamentals.load_daily.plist` skeleton:

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

Load it with `launchctl load ~/Library/LaunchAgents/com.fundamentals.load_daily.plist`.

## Dev commands

```bash
uv run pytest
uv run ruff check . && uv run black --check .
uv run streamlit run src/app/Home.py
```

## Configuration

- **Secrets** — `.env`, never committed. Copy from `.env.example`.
- **Settings** — `config/settings.yml` (paths, throttles, benchmark
  ticker, archive retention).
- **Initial universe** — `config/universe.yml`. Seed only; runtime
  source of truth is the `universe` table.

## Vendor

[EODHD](https://eodhd.com/). The free tier covers an MVP universe; paid
tiers unlock more fundamentals history and faster rate limits. The
shipped throttles in `config/settings.yml` are tuned for a paid plan —
tune downward for the free tier or upward for higher tiers.
