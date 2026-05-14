"""
Phase 13A: Forward screens powered by vendor-provided trend and revision data.

These screens work on day 1 because EODHD pre-computes 7/30/60/90-day
deltas for EPS estimates and revision counts per future fiscal period.
"""

import duckdb
import pandas as pd


def _latest_estimates(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Latest snapshot rows from analyst_estimates_history for active universe."""
    return con.execute("""
        WITH latest AS (
            SELECT ticker, MAX(snapshot_date) AS snap
            FROM analyst_estimates_history
            WHERE ticker IN (SELECT ticker FROM universe WHERE active)
            GROUP BY ticker
        )
        SELECT aeh.*
        FROM analyst_estimates_history aeh
        JOIN latest l ON aeh.ticker = l.ticker AND aeh.snapshot_date = l.snap
    """).df()


def screen_eps_revised_up(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 30,
    min_delta_pct: float = 0.0,
    period_filter: str | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers where EPS estimate has been revised up over the past N days.

    lookback_days: 7 or 30 (vendor provides both)
    min_delta_pct: minimum % change required (0 = any upward revision)
    period_filter: vendor period code e.g. '0q', '+1q', '0y', '+1y', or None for all
    """
    df = _latest_estimates(con)
    if df.empty:
        return pd.DataFrame()

    trend_col = "eps_trend_7days_ago" if lookback_days == 7 else "eps_trend_30days_ago"

    if period_filter:
        df = df[df["period"] == period_filter]

    df = df[df["eps_trend_current"].notna() & df[trend_col].notna() & (df[trend_col] != 0)]
    df["eps_delta"] = df["eps_trend_current"] - df[trend_col]
    df["eps_delta_pct"] = df["eps_delta"] / df[trend_col].abs() * 100

    df = df[df["eps_delta"] > 0]
    if min_delta_pct > 0:
        df = df[df["eps_delta_pct"] >= min_delta_pct]

    result = (
        df.groupby("ticker")
        .agg(
            periods_revised_up=("eps_delta", "count"),
            max_eps_delta_pct=("eps_delta_pct", "max"),
            avg_eps_current=("eps_trend_current", "mean"),
        )
        .reset_index()
        .sort_values("max_eps_delta_pct", ascending=False)
    )

    result = _add_security_info(con, result)
    if display_filter is not None:
        result = result[result["ticker"].isin(display_filter)]
    return result.reset_index(drop=True)


def screen_net_upward_eps_revisions(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 30,
    min_net: int = 1,
    period_filter: str | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers with net upward EPS analyst revisions (upgrades minus downgrades >= min_net).

    lookback_days: 7 or 30
    min_net: minimum net upward revisions required
    """
    df = _latest_estimates(con)
    if df.empty:
        return pd.DataFrame()

    if lookback_days == 7:
        up_col, down_col = "eps_revisions_up_last_7days", "eps_revisions_down_last_7days"
    else:
        up_col, down_col = "eps_revisions_up_last_30days", "eps_revisions_down_last_30days"

    if period_filter:
        df = df[df["period"] == period_filter]

    df = df[df[up_col].notna() | df[down_col].notna()]
    df["net_revisions"] = df[up_col].fillna(0) - df[down_col].fillna(0)

    agg = (
        df.groupby("ticker")
        .agg(
            net_revisions=("net_revisions", "sum"),
            revisions_up=pd.NamedAgg(column=up_col, aggfunc="sum"),
            revisions_down=pd.NamedAgg(column=down_col, aggfunc="sum"),
        )
        .reset_index()
    )
    agg = agg[agg["net_revisions"] >= min_net].sort_values("net_revisions", ascending=False)

    agg = _add_security_info(con, agg)
    if display_filter is not None:
        agg = agg[agg["ticker"].isin(display_filter)]
    return agg.reset_index(drop=True)


def screen_beat_and_revise(
    con: duckdb.DuckDBPyConnection,
    *,
    min_surprise_pct: float = 0.0,
    min_eps_delta_pct: float = 0.0,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers that beat latest EPS estimate AND had subsequent upward forward revision.

    min_surprise_pct: minimum EPS surprise % required (0 = any positive surprise)
    min_eps_delta_pct: minimum forward EPS revision % required
    """
    # Get latest earnings event with positive surprise
    beats = con.execute(
        """
        WITH ranked AS (
            SELECT ticker, fiscal_period_end, eps_estimate, eps_actual, surprise_percent,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fiscal_period_end DESC) AS rn
            FROM earnings_events
            WHERE eps_actual IS NOT NULL AND surprise_percent > ?
              AND ticker IN (SELECT ticker FROM universe WHERE active)
        )
        SELECT ticker, fiscal_period_end, eps_estimate, eps_actual, surprise_percent
        FROM ranked WHERE rn = 1
    """,
        [min_surprise_pct],
    ).df()

    if beats.empty:
        return pd.DataFrame()

    # Get current vs 30-day-ago EPS trend for the nearest future period
    estimates = _latest_estimates(con)
    if estimates.empty:
        return pd.DataFrame()

    # Pick nearest future period per ticker
    future = estimates[
        estimates["eps_trend_current"].notna()
        & estimates["eps_trend_30days_ago"].notna()
        & (estimates["eps_trend_30days_ago"] != 0)
    ].copy()
    future["eps_delta_pct"] = (
        (future["eps_trend_current"] - future["eps_trend_30days_ago"])
        / future["eps_trend_30days_ago"].abs()
        * 100
    )
    future = future[future["eps_delta_pct"] >= min_eps_delta_pct]

    nearest = (
        future.sort_values("period_end")
        .groupby("ticker")
        .first()
        .reset_index()[
            [
                "ticker",
                "period",
                "period_end",
                "eps_trend_current",
                "eps_trend_30days_ago",
                "eps_delta_pct",
            ]
        ]
    )

    result = beats.merge(nearest, on="ticker")
    result = result.sort_values(["eps_delta_pct", "surprise_percent"], ascending=False)
    result = _add_security_info(con, result)
    if display_filter is not None:
        result = result[result["ticker"].isin(display_filter)]
    return result.reset_index(drop=True)


def _add_security_info(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ticker" not in df.columns:
        return df
    info = con.execute("""
        SELECT ticker, name, sector FROM security_master
        WHERE ticker IN (SELECT ticker FROM universe WHERE active)
    """).df()
    return df.merge(info, on="ticker", how="left")
