import logging
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from .ingest.orchestrator import fetch_and_ingest

log = logging.getLogger(__name__)


def add_ticker(con: duckdb.DuckDBPyConnection, ticker: str, notes: str | None = None) -> None:
    """Fetch and ingest all history for ticker, then upsert it into the universe table."""
    fetch_and_ingest(con, ticker)
    con.execute(
        "INSERT INTO universe (ticker, added_at, active, notes) VALUES (?, now(), true, ?)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true",
        [ticker, notes],
    )
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
