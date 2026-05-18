import json
import logging
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import duckdb
import yaml

from .fetch import fetch_fundamentals, fetch_prices
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

    t0 = time.monotonic()
    try:
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
        _record_load_run(con, ticker, "ok", int((time.monotonic() - t0) * 1000))
    except Exception as exc:
        _record_load_run(con, ticker, "failed", int((time.monotonic() - t0) * 1000), str(exc))
        raise


def _record_load_run(
    con: duckdb.DuckDBPyConnection,
    ticker: str,
    status: str,
    duration_ms: int,
    error_message: str | None = None,
) -> None:
    try:
        con.execute(
            "INSERT INTO load_runs (ticker, status, duration_ms, error_message) VALUES (?, ?, ?, ?)",
            [ticker, status, duration_ms, error_message],
        )
    except Exception:
        log.warning("could not write load_run ticker=%s", ticker)


def ingest_universe(con: duckdb.DuckDBPyConnection) -> list[tuple[str, bool, str | None]]:
    """Fetch and ingest all active tickers in the universe table.

    Returns a list of (ticker, success, error_message) tuples so the caller
    can summarize. Failures are logged but never re-raised — one bad ticker
    must not break the rest of the load.
    """
    tickers = [r[0] for r in con.execute("SELECT ticker FROM universe WHERE active").fetchall()]
    log.info("ingesting %d active tickers", len(tickers))
    results: list[tuple[str, bool, str | None]] = []
    for ticker in tickers:
        try:
            fetch_and_ingest(con, ticker)
            results.append((ticker, True, None))
        except Exception as exc:
            log.exception("fetch_and_ingest failed ticker=%s", ticker)
            results.append((ticker, False, str(exc)))
    return results


def _fetch_ticker_files(ticker: str, cfg: dict) -> tuple[Path, Path]:
    """Fetch and write raw JSON files for one ticker. No DB access.

    Always fetches fresh data from the vendor, bypassing the _fresh_today guard.
    Intended for the "Refresh All" path where the user explicitly wants new data.
    """
    paths = cfg.get("paths", {})
    raw_fund_dir = Path(paths.get("raw_fundamentals", "data/raw/fundamentals"))
    raw_price_dir = Path(paths.get("raw_prices", "data/raw/prices"))
    archive_dir = Path(paths.get("archive", "data/archive"))
    do_archive = cfg.get("ingest", {}).get("archive_raw_files", True)

    raw_fund_dir.mkdir(parents=True, exist_ok=True)
    raw_price_dir.mkdir(parents=True, exist_ok=True)

    fund_path = raw_fund_dir / f"{ticker}.json"
    price_path = raw_price_dir / f"{ticker}.json"

    fund_data = fetch_fundamentals(ticker)
    fund_path.write_text(json.dumps(fund_data))

    price_data = fetch_prices(ticker)
    price_path.write_text(json.dumps(price_data))

    if do_archive:
        today = date.today().isoformat()
        arch = archive_dir / today
        arch.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fund_path, arch / f"{ticker}-fundamentals.json")
        shutil.copy2(price_path, arch / f"{ticker}-prices.json")

    return fund_path, price_path


def refresh_universe_threaded(
    con: duckdb.DuckDBPyConnection,
    max_workers: int = 3,
) -> list[tuple[str, bool, str | None]]:
    """Refresh all active tickers: parallel HTTP fetches, then serial DB writes.

    Threads are used only for the network fetch phase. All DuckDB writes are
    serialized in the caller's thread, preserving the single-writer guarantee.
    """
    tickers = [r[0] for r in con.execute("SELECT ticker FROM universe WHERE active").fetchall()]
    log.info("refreshing %d active tickers (max_workers=%d)", len(tickers), max_workers)
    cfg = _settings()

    fetched: dict[str, tuple[Path, Path]] = {}
    fetch_errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_ticker_files, t, cfg): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                fetched[ticker] = future.result()
            except Exception as exc:
                log.exception("fetch failed ticker=%s", ticker)
                fetch_errors[ticker] = str(exc)

    results: list[tuple[str, bool, str | None]] = []
    for ticker in tickers:
        if ticker in fetch_errors:
            _record_load_run(con, ticker, "failed", 0, fetch_errors[ticker])
            results.append((ticker, False, fetch_errors[ticker]))
            continue
        t0 = time.monotonic()
        fund_path, price_path = fetched[ticker]
        try:
            ingest_ticker(con, fund_path, price_path, ticker=ticker)
            _record_load_run(con, ticker, "ok", int((time.monotonic() - t0) * 1000))
            results.append((ticker, True, None))
        except Exception as exc:
            log.exception("ingest failed ticker=%s", ticker)
            _record_load_run(con, ticker, "failed", int((time.monotonic() - t0) * 1000), str(exc))
            results.append((ticker, False, str(exc)))

    return results


def _fresh_today(path: Path) -> bool:
    """Return True if path exists and was written today."""
    if not path.exists():
        return False
    mtime = date.fromtimestamp(path.stat().st_mtime)
    return mtime == date.today()
