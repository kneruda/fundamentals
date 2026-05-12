# Fundamentals Dashboard

A personal equity fundamentals dashboard powered by EODHD data. Tracks
valuation, profitability, growth, balance-sheet strength, and analyst
expectations for a user-managed universe of stocks.

See [`AGENTS.md`](AGENTS.md) for design guidance and [`PLAN.md`](PLAN.md)
for the phased implementation roadmap.

## Quickstart

```bash
# 1. Install dependencies
uv sync

# 2. Configure your EODHD API token
cp .env.example .env
# Edit .env and set EODHD_API_TOKEN

# 3. Run tests + linting
uv run pytest
uv run ruff check .
uv run black --check .

# 4. Seed the warehouse with the initial universe (Phase 3+)
uv run python scripts/seed_universe.py

# 5. Add or remove tickers later
uv run python scripts/add_ticker.py SHOP

# 6. Daily refresh (schedule this via cron after Phase 6)
uv run python scripts/load_daily.py

# 7. Launch the dashboard (Phase 5+)
uv run streamlit run src/app/Home.py
```

## Status

This project is built in phases — see `PLAN.md`. Not every command above
works in every phase; the README lists the eventual full surface.

## Project layout

See [`AGENTS.md`](AGENTS.md) → "Repository layout".

## Configuration

- **Secrets** (API tokens): `.env`, never committed.
- **Settings** (paths, throttles, defaults): `config/settings.yml`.
- **Initial universe**: `config/universe.yml` (seed only; runtime source of
  truth is the `universe` table in the warehouse).

## Scheduling the daily load

`scripts/load_daily.py` should run once per day after US market close (~17:00 ET)
to capture fresh fundamentals and analyst snapshots. At least 30 days of snapshots
are needed before forward-looking screens (Phase 9) produce signal.

### macOS / Linux (cron)

```bash
crontab -e
```

Add a line (runs at 17:30 ET = 21:30 UTC Mon–Fri):

```
30 21 * * 1-5 cd /path/to/fundamentals && uv run python scripts/load_daily.py >> data/logs/load_daily.log 2>&1
```

Create the log directory first: `mkdir -p data/logs`.

### macOS (launchd)

Create `~/Library/LaunchAgents/com.fundamentals.load_daily.plist`:

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
        <key>Hour</key>          <integer>17</integer>
        <key>Minute</key>        <integer>30</integer>
    </dict>
    <key>StandardOutPath</key>   <string>/path/to/fundamentals/data/logs/load_daily.log</string>
    <key>StandardErrorPath</key> <string>/path/to/fundamentals/data/logs/load_daily.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>EODHD_API_TOKEN</key> <string>your_token_here</string>
    </dict>
</dict>
</plist>
```

Load it: `launchctl load ~/Library/LaunchAgents/com.fundamentals.load_daily.plist`

## Vendor

Data comes from [EODHD](https://eodhd.com/). The free tier covers the MVP
universe; higher tiers unlock more fundamentals history and faster
rate limits.
