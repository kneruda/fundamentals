import logging
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from .ingest.orchestrator import fetch_and_ingest

log = logging.getLogger(__name__)


def add_ticker(con: duckdb.DuckDBPyConnection, ticker: str, notes: str | None = None) -> None:
    """Fetch and ingest all history for ticker, then upsert it into the universe table.

    For a brand-new ticker a pending (active=false) row is written before ingest starts,
    so warehouse data is always traceable to a universe entry. If ingest fails the
    pending row is removed. For an existing ticker the row is left as-is until ingest
    succeeds, then set active=true and notes updated.
    """
    existing = con.execute("SELECT ticker FROM universe WHERE ticker = ?", [ticker]).fetchone()
    is_new = existing is None

    if is_new:
        con.execute(
            "INSERT INTO universe (ticker, added_at, active, notes) VALUES (?, now(), false, ?)",
            [ticker, notes],
        )
    elif notes is not None:
        con.execute("UPDATE universe SET notes = ? WHERE ticker = ?", [notes, ticker])

    try:
        fetch_and_ingest(con, ticker)
    except Exception:
        if is_new:
            con.execute("DELETE FROM universe WHERE ticker = ?", [ticker])
        raise

    con.execute("UPDATE universe SET active = true WHERE ticker = ?", [ticker])
    log.info("added ticker=%s", ticker)


def remove_ticker(con: duckdb.DuckDBPyConnection, ticker: str) -> None:
    """Soft-delete ticker from the universe (sets active = false, data preserved)."""
    con.execute("UPDATE universe SET active = false WHERE ticker = ?", [ticker])
    log.info("removed ticker=%s", ticker)


def list_universe(con: duckdb.DuckDBPyConnection, active_only: bool = True) -> pd.DataFrame:
    sql = "SELECT ticker, added_at, active, notes FROM universe"
    if active_only:
        sql += " WHERE active = true"
    sql += " ORDER BY ticker"
    return con.execute(sql).df()


def parse_tickers(text: str) -> list[str]:
    from .ticker_input import parse_ticker_input

    return parse_ticker_input(text)


def bulk_add_tickers(
    con: duckdb.DuckDBPyConnection, tickers: list[str]
) -> list[tuple[str, bool, str]]:
    """Add multiple tickers, continuing past individual failures.

    Returns a list of (ticker, success, message) tuples.
    """
    results = []
    for ticker in tickers:
        was_present = (
            con.execute("SELECT COUNT(*) FROM universe WHERE ticker = ?", [ticker]).fetchone()[0]
            > 0
        )
        try:
            add_ticker(con, ticker)
            msg = "already present, refreshed" if was_present else "added"
            results.append((ticker, True, msg))
        except Exception as exc:
            log.warning("bulk_add failed ticker=%s: %s", ticker, exc)
            results.append((ticker, False, str(exc)))
    return results


def seed_from_config(con: duckdb.DuckDBPyConnection, yaml_path: Path) -> None:
    """Add tickers from a YAML seed file that are not already in the universe table."""
    with yaml_path.open() as f:
        cfg = yaml.safe_load(f)
    existing = {r[0] for r in con.execute("SELECT ticker FROM universe").fetchall()}
    for ticker in cfg.get("tickers", []):
        if ticker in existing:
            log.info("skip existing ticker=%s", ticker)
            continue
        log.info("seeding ticker=%s", ticker)
        try:
            add_ticker(con, ticker)
        except Exception:
            log.exception("failed to seed ticker=%s", ticker)
