# Fundamentals Dashboard

A personal equity fundamentals dashboard powered by EODHD data. Tracks
valuation, profitability, growth, balance-sheet strength, and analyst
expectations for a user-managed universe of stocks.

See [`AGENTS.md`](AGENTS.md) for design guidance and [`PLAN.md`](PLAN.md)
for the phased implementation roadmap.

---

## Quickstart (local dev)

```bash
# 1. Install dependencies
uv sync

# 2. Configure your EODHD API token
cp .env.example .env
# Edit .env and set EODHD_API_TOKEN=<your_token>

# 3. Seed the warehouse with the initial universe (~10 tickers)
uv run python scripts/seed_universe.py

# 4. Launch the dashboard
uv run streamlit run src/app/Home.py
```

The dashboard opens at http://localhost:8501. Use the **Universe** page to
add/remove tickers, view load status, and run bulk uploads from there.

---

## Quickstart (Docker)

```bash
# Build images
docker compose build

# One-shot: seed + daily load
docker compose run --rm app uv run python scripts/seed_universe.py
docker compose run --rm app uv run python scripts/load_daily.py

# Long-running: launch the UI
docker compose up streamlit
```

Or use the Makefile shortcuts:

```bash
make load    # run load_daily.py via Docker
make ui      # start Streamlit on port 8501
make shell   # open a bash shell inside the container
make test    # run pytest inside the container
```

Both workflows mount `./data` and `./.env` into the container, so the
warehouse and API token are shared between host and container.

---

## Bulk-loading a large universe

To load hundreds of tickers at once with rate limiting and resumable
checkpointing:

```bash
# Create a text file with one ticker per line (# comments and blank lines ignored)
uv run python scripts/bulk_load.py --file path/to/tickers.txt

# If the job is interrupted, resume it with the printed job ID
uv run python scripts/bulk_load.py --resume <job_id>
```

Default throttle: 20 tickers/min (configurable in `config/settings.yml`
under `bulk_load.requests_per_minute`). Each ticker makes 2 API calls
(fundamentals + prices). Adjust upward once you confirm your EODHD tier.

---

## Other scripts

```bash
uv run python scripts/add_ticker.py SHOP      # add a single ticker
uv run python scripts/load_daily.py           # daily refresh (all active tickers)
uv run python scripts/rebuild.py              # rebuild warehouse from local raw files
uv run python scripts/seed_universe.py        # (re-)seed from config/universe.yml
```

---

## Scheduling the daily load

Run `scripts/load_daily.py` once per day after US market close. At least
30 days of analyst snapshots are needed before forward-looking screens
produce signal.

> **DuckDB constraint**: only one writer at a time. Schedule loads during
> quiet hours so they don't conflict with an open Streamlit session.
> The default cron schedule (02:00 local) avoids this in practice.

### Cron (macOS / Linux)

See [`scripts/cron.example`](scripts/cron.example) for a ready-to-paste
snippet. Quick setup:

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
        <key>Hour</key>   <integer>2</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>   <string>/path/to/fundamentals/data/logs/load_daily.log</string>
    <key>StandardErrorPath</key> <string>/path/to/fundamentals/data/logs/load_daily.err</string>
</dict>
</plist>
```

Load it: `launchctl load ~/Library/LaunchAgents/com.fundamentals.load_daily.plist`

---

## Dev commands

```bash
uv run pytest                             # run tests
uv run ruff check . && uv run black --check .   # lint + format check
uv run python scripts/load_daily.py      # fetch + ingest universe
uv run python scripts/rebuild.py         # full rebuild from raw (no fetch)
uv run streamlit run src/app/Home.py     # launch dashboard
```

---

## Configuration

- **Secrets** (API token): `.env` — never committed. Copy from `.env.example`.
- **Settings** (paths, throttles, defaults): `config/settings.yml`.
- **Initial universe**: `config/universe.yml` (seed only; runtime source of
  truth is the `universe` table in the warehouse).

---

## Vendor

Data comes from [EODHD](https://eodhd.com/). The free tier covers the MVP
universe; higher tiers unlock more fundamentals history and faster rate limits.
