"""Watchlist selection helpers without UI state or Streamlit dependencies."""

import duckdb
import pandas as pd

from src.watchlist import get_membership, list_watchlists


def available_watchlists(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return the watchlists available to a UI, ordered by their stored name."""
    return list_watchlists(con)


def display_filter_for_watchlist(
    con: duckdb.DuckDBPyConnection, watchlist_id: int | None
) -> list[str] | None:
    """Resolve a nullable watchlist ID to its display ticker filter.

    ``None`` represents the full universe. Comparison-universe calculations
    remain the responsibility of the existing screen functions.
    """
    if watchlist_id is None:
        return None
    return get_membership(con, watchlist_id)
