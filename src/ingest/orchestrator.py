import json
import logging
import shutil
from datetime import date
from pathlib import Path

import duckdb
import yaml

from .sections.analyst_snapshot import ingest_analyst_snapshot
from .sections.dividends import ingest_dividends
from .sections.earnings import ingest_earnings
from .sections.financials import ingest_financials
from .sections.general import ingest_general, ingest_highlights
from .sections.prices import ingest_prices
from .sections.shares import ingest_shares

log = logging.getLogger(__name__)

_SECTIONS = [
    ("general", ingest_general),
    ("highlights", ingest_highlights),
    ("financials", ingest_financials),
    ("earnings", ingest_earnings),
    ("shares", ingest_shares),
    ("dividends", ingest_dividends),
    ("analyst_snapshot", ingest_analyst_snapshot),
    ("prices", ingest_prices),
]

_settings_path = Path(__file__).parent.parent.parent / "config" / "settings.yml"


def _settings() -> dict:
    with _settings_path.open() as f:
        return yaml.safe_load(f)


def ingest_ticker(
    con: duckdb.DuckDBPyConnection,
    fundamentals_path: str | Path,
    prices_path: str | Path | None = None,
    *,
    ticker: str | None = None,
) -> None:
    """Parse fundamentals JSON (and optionally prices JSON) and load all sections."""
    path = Path(fundamentals_path)
    with path.open() as f:
        data = json.load(f)

    if ticker is None:
        ticker = data.get("General", {}).get("Code") or path.stem

    if prices_path is not None:
        with Path(prices_path).open() as f:
            data["_prices"] = json.load(f)

    for name, fn in _SECTIONS:
        try:
            fn(con, ticker, data)
        except Exception:
            log.exception("section=%s ticker=%s", name, ticker)


def fetch_and_ingest(con: duckdb.DuckDBPyConnection, ticker: str) -> None:
    """Fetch fresh data from EODHD, optionally archive, then ingest."""
    from .fetch import fetch_fundamentals, fetch_prices

    cfg = _settings()
    paths = cfg.get("paths", {})
    ingest_cfg = cfg.get("ingest", {})

    raw_fund_dir = Path(paths.get("raw_fundamentals", "data/raw/fundamentals"))
    raw_price_dir = Path(paths.get("raw_prices", "data/raw/prices"))
    archive_dir = Path(paths.get("archive", "data/archive"))
    do_archive = ingest_cfg.get("archive_raw_files", True)

    raw_fund_dir.mkdir(parents=True, exist_ok=True)
    raw_price_dir.mkdir(parents=True, exist_ok=True)

    fund_path = raw_fund_dir / f"{ticker}.json"
    price_path = raw_price_dir / f"{ticker}.json"

    today = date.today().isoformat()

    if not _fresh_today(fund_path):
        log.info("fetching fundamentals ticker=%s", ticker)
        fund_data = fetch_fundamentals(ticker)
        fund_path.write_text(json.dumps(fund_data))

    if not _fresh_today(price_path):
        log.info("fetching prices ticker=%s", ticker)
        price_data = fetch_prices(ticker)
        price_path.write_text(json.dumps(price_data))

    if do_archive:
        arch = archive_dir / today
        arch.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fund_path, arch / f"{ticker}-fundamentals.json")
        shutil.copy2(price_path, arch / f"{ticker}-prices.json")

    ingest_ticker(con, fund_path, price_path, ticker=ticker)


def ingest_universe(con: duckdb.DuckDBPyConnection) -> None:
    """Fetch and ingest all active tickers in the universe table."""
    tickers = [r[0] for r in con.execute("SELECT ticker FROM universe WHERE active").fetchall()]
    log.info("ingesting %d active tickers", len(tickers))
    for ticker in tickers:
        try:
            fetch_and_ingest(con, ticker)
        except Exception:
            log.exception("fetch_and_ingest failed ticker=%s", ticker)


def _fresh_today(path: Path) -> bool:
    """Return True if path exists and was written today."""
    if not path.exists():
        return False
    mtime = date.fromtimestamp(path.stat().st_mtime)
    return mtime == date.today()
