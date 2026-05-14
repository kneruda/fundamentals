"""Watchlist CRUD operations."""

import duckdb
import pandas as pd


def _next_id(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT COALESCE(MAX(watchlist_id), 0) + 1 FROM watchlist").fetchone()[0]


def create_watchlist(
    con: duckdb.DuckDBPyConnection,
    name: str,
    tickers: list[str],
    description: str | None = None,
) -> int:
    """Create a named watchlist and return its watchlist_id."""
    wid = _next_id(con)
    con.execute(
        "INSERT INTO watchlist (watchlist_id, name, description) VALUES (?, ?, ?)",
        [wid, name, description],
    )
    for ticker in tickers:
        con.execute(
            "INSERT OR IGNORE INTO watchlist_membership (watchlist_id, ticker) VALUES (?, ?)",
            [wid, ticker],
        )
    return wid


def delete_watchlist(con: duckdb.DuckDBPyConnection, name_or_id: str | int) -> None:
    """Delete a watchlist and all its memberships."""
    wid = _resolve_id(con, name_or_id)
    con.execute("DELETE FROM watchlist_membership WHERE watchlist_id = ?", [wid])
    con.execute("DELETE FROM watchlist WHERE watchlist_id = ?", [wid])


def rename_watchlist(con: duckdb.DuckDBPyConnection, old_name: str, new_name: str) -> None:
    con.execute(
        "UPDATE watchlist SET name = ?, updated_at = now() WHERE lower(name) = lower(?)",
        [new_name, old_name],
    )


def list_watchlists(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT w.watchlist_id, w.name, w.description, w.created_at,
               COUNT(wm.ticker) AS member_count
        FROM watchlist w
        LEFT JOIN watchlist_membership wm ON w.watchlist_id = wm.watchlist_id
        GROUP BY w.watchlist_id, w.name, w.description, w.created_at
        ORDER BY w.name
    """).df()


def get_membership(con: duckdb.DuckDBPyConnection, watchlist_id_or_name: int | str) -> list[str]:
    """Return ordered ticker list for a watchlist."""
    wid = _resolve_id(con, watchlist_id_or_name)
    rows = con.execute(
        "SELECT ticker FROM watchlist_membership WHERE watchlist_id = ? ORDER BY ticker",
        [wid],
    ).fetchall()
    return [r[0] for r in rows]


def _resolve_id(con: duckdb.DuckDBPyConnection, name_or_id: str | int) -> int:
    if isinstance(name_or_id, int):
        return name_or_id
    row = con.execute(
        "SELECT watchlist_id FROM watchlist WHERE lower(name) = lower(?)", [name_or_id]
    ).fetchone()
    if not row:
        raise ValueError(f"Watchlist not found: {name_or_id!r}")
    return row[0]
