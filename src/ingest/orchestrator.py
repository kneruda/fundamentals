import json
import logging
from pathlib import Path

import duckdb

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


def ingest_ticker(con: duckdb.DuckDBPyConnection, fundamentals_path: str | Path) -> None:
    """Parse fundamentals JSON and load all sections into the warehouse."""
    path = Path(fundamentals_path)
    with path.open() as f:
        data = json.load(f)

    ticker = data.get("General", {}).get("Code") or path.stem

    for name, fn in _SECTIONS:
        try:
            fn(con, ticker, data)
        except Exception:
            log.exception("section=%s ticker=%s", name, ticker)
