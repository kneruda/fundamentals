"""
Phase 13B: Forward screens requiring accumulated daily_forward_snapshot history.

These screens require at least min_history_days of daily snapshots per ticker.
Tickers below the threshold are excluded; the caller receives a count of excluded tickers.
"""

import duckdb
import pandas as pd


def _snapshot_days(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Days of snapshot history per active ticker."""
    return con.execute("""
        SELECT ticker, COUNT(DISTINCT snapshot_date) AS n_days,
               MIN(snapshot_date) AS first_snap, MAX(snapshot_date) AS last_snap
        FROM daily_forward_snapshot
        WHERE ticker IN (SELECT ticker FROM universe WHERE active)
        GROUP BY ticker
    """).df()


def screen_consensus_rating_shift(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 30,
    min_shift: float = 0.5,
    min_history_days: int = 30,
    display_filter: list[str] | None = None,
) -> tuple[pd.DataFrame, int]:
    """Tickers where consensus analyst rating shifted by min_shift over lookback_days.

    Returns (result_df, n_excluded_insufficient_history).
    Rating scale: 1 = Strong Buy, 5 = Strong Sell. Negative shift = upgrade.
    """
    coverage = _snapshot_days(con)
    eligible = coverage[coverage["n_days"] >= min_history_days]["ticker"].tolist()
    n_excluded = len(coverage) - len(eligible)

    if not eligible:
        return pd.DataFrame(), n_excluded

    tickers_sql = ", ".join(f"'{t}'" for t in eligible)

    df = con.execute(f"""
        WITH latest AS (
            SELECT ticker, snapshot_date, consensus_rating,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY snapshot_date DESC) AS rn
            FROM daily_forward_snapshot
            WHERE ticker IN ({tickers_sql})
        ),
        past AS (
            SELECT ticker, snapshot_date, consensus_rating,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker
                       ORDER BY ABS(DATEDIFF('day', snapshot_date,
                           (SELECT MAX(snapshot_date) FROM daily_forward_snapshot WHERE ticker = dfs.ticker)
                           - {lookback_days})
                       )
                   ) AS rn
            FROM daily_forward_snapshot dfs
            WHERE ticker IN ({tickers_sql})
        )
        SELECT l.ticker,
               l.consensus_rating AS rating_now,
               p.consensus_rating AS rating_then,
               l.consensus_rating - p.consensus_rating AS rating_shift,
               l.snapshot_date AS last_snap
        FROM latest l
        JOIN past p ON l.ticker = p.ticker AND l.rn = 1 AND p.rn = 1
        WHERE l.consensus_rating IS NOT NULL
          AND p.consensus_rating IS NOT NULL
          AND ABS(l.consensus_rating - p.consensus_rating) >= {min_shift}
        ORDER BY l.consensus_rating - p.consensus_rating
    """).df()

    df = _add_security_info(con, df)
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True), n_excluded


def screen_target_price_raised(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 30,
    min_change_pct: float = 5.0,
    min_history_days: int = 30,
    display_filter: list[str] | None = None,
) -> tuple[pd.DataFrame, int]:
    """Tickers where analyst target price rose by at least min_change_pct over lookback_days.

    Returns (result_df, n_excluded_insufficient_history).
    """
    coverage = _snapshot_days(con)
    eligible = coverage[coverage["n_days"] >= min_history_days]["ticker"].tolist()
    n_excluded = len(coverage) - len(eligible)

    if not eligible:
        return pd.DataFrame(), n_excluded

    tickers_sql = ", ".join(f"'{t}'" for t in eligible)

    df = con.execute(f"""
        WITH snapshots AS (
            SELECT ticker, snapshot_date, target_price
            FROM daily_forward_snapshot
            WHERE ticker IN ({tickers_sql}) AND target_price IS NOT NULL
        ),
        latest AS (
            SELECT ticker, snapshot_date AS last_snap, target_price AS tp_now,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY snapshot_date DESC) AS rn
            FROM snapshots
        ),
        past AS (
            SELECT ticker, snapshot_date, target_price AS tp_then,
                   ROW_NUMBER() OVER (
                       PARTITION BY ticker
                       ORDER BY ABS(DATEDIFF('day', snapshot_date,
                           (SELECT MAX(snapshot_date) FROM daily_forward_snapshot WHERE ticker = s.ticker)
                           - {lookback_days})
                       )
                   ) AS rn
            FROM snapshots s
        )
        SELECT l.ticker, l.tp_now, p.tp_then,
               (l.tp_now / NULLIF(p.tp_then, 0) - 1) * 100 AS tp_change_pct,
               l.last_snap
        FROM latest l
        JOIN past p ON l.ticker = p.ticker AND l.rn = 1 AND p.rn = 1
        WHERE (l.tp_now / NULLIF(p.tp_then, 0) - 1) * 100 >= {min_change_pct}
        ORDER BY (l.tp_now / NULLIF(p.tp_then, 0) - 1) * 100 DESC
    """).df()

    df = _add_security_info(con, df)
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True), n_excluded


def _add_security_info(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df
    info = con.execute("""
        SELECT ticker, name, sector FROM security_master
        WHERE ticker IN (SELECT ticker FROM universe WHERE active)
    """).df()
    return df.merge(info, on="ticker", how="left")
