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

## Vendor

Data comes from [EODHD](https://eodhd.com/). The free tier covers the MVP
universe; higher tiers unlock more fundamentals history and faster
rate limits.
