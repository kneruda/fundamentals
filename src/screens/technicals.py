"""Technical indicator screens over the active universe.

Each function returns a DataFrame of matching tickers with the columns that
drove the filter (why they qualified). SQL runs over the full active universe;
display_filter is applied last in Python.
"""

import duckdb
import pandas as pd

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_LATEST_TECH_SQL = """
    WITH latest_tech AS (
        SELECT t.*
        FROM technicals_daily t
        JOIN (SELECT ticker, MAX(date) AS mx FROM technicals_daily GROUP BY ticker) lt
            ON t.ticker = lt.ticker AND t.date = lt.mx
    )
    SELECT
        u.ticker,
        sm.name,
        sm.sector,
        lt.date,
        lt.adjusted_close,
        lt.sma_20,
        lt.sma_50,
        lt.sma_200,
        lt.ema_12,
        lt.ema_26,
        lt.ema_50,
        lt.rsi_14,
        lt.macd,
        lt.macd_signal,
        lt.macd_histogram,
        lt.bb_width,
        lt.pct_from_sma_50,
        lt.pct_from_sma_200,
        lt.pct_from_52w_high,
        lt.pct_from_52w_low,
        lt.volume_ratio,
        sz.mktcap_b,
        sz.adtv_20d_m
    FROM universe u
    LEFT JOIN security_master sm       ON u.ticker = sm.ticker
    LEFT JOIN latest_tech lt           ON u.ticker = lt.ticker
    LEFT JOIN universe_size_latest sz  ON u.ticker = sz.ticker
    WHERE u.active = true
    ORDER BY sm.sector NULLS LAST, u.ticker
"""


def _base_df(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(_LATEST_TECH_SQL).df()


def _apply_size_filter(
    df: pd.DataFrame, min_mktcap_b: float | None, min_adtv_m: float | None
) -> pd.DataFrame:
    if min_mktcap_b is not None:
        df = df[df["mktcap_b"].notna() & (df["mktcap_b"] >= min_mktcap_b)]
    if min_adtv_m is not None:
        df = df[df["adtv_20d_m"].notna() & (df["adtv_20d_m"] >= min_adtv_m)]
    return df


def _finish(df: pd.DataFrame, display_filter: list[str] | None, cols: list[str]) -> pd.DataFrame:
    df = df[cols].copy()
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Trend screens
# ---------------------------------------------------------------------------


def screen_confirmed_uptrend(
    con: duckdb.DuckDBPyConnection,
    *,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Price > SMA200 and SMA50 > SMA200."""
    df = _base_df(con)
    df = df[
        df["sma_200"].notna()
        & df["sma_50"].notna()
        & (df["adjusted_close"] > df["sma_200"])
        & (df["sma_50"] > df["sma_200"])
    ]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "adjusted_close",
            "sma_50",
            "sma_200",
            "pct_from_sma_200",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_confirmed_downtrend(
    con: duckdb.DuckDBPyConnection,
    *,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Price < SMA200 and SMA50 < SMA200."""
    df = _base_df(con)
    df = df[
        df["sma_200"].notna()
        & df["sma_50"].notna()
        & (df["adjusted_close"] < df["sma_200"])
        & (df["sma_50"] < df["sma_200"])
    ]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "adjusted_close",
            "sma_50",
            "sma_200",
            "pct_from_sma_200",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_golden_cross_recent(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 30,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """SMA50 crossed above SMA200 within the last N days."""
    crossed = con.execute(f"""
        WITH latest_dates AS (
            SELECT ticker, MAX(date) AS latest_date FROM technicals_daily GROUP BY ticker
        ),
        cross_events AS (
            SELECT t.ticker,
                   LAG(t.sma_50 - t.sma_200) OVER (PARTITION BY t.ticker ORDER BY t.date) AS prev_diff,
                   t.sma_50 - t.sma_200 AS curr_diff,
                   t.date AS cross_date
            FROM technicals_daily t
            JOIN latest_dates ld ON t.ticker = ld.ticker
            WHERE t.date >= ld.latest_date - INTERVAL {lookback_days + 1} DAY
              AND t.sma_50 IS NOT NULL AND t.sma_200 IS NOT NULL
        )
        SELECT DISTINCT ticker FROM cross_events
        WHERE prev_diff < 0 AND curr_diff >= 0
        """).df()
    crossed_tickers = set(crossed["ticker"].tolist())

    df = _base_df(con)
    df = df[df["ticker"].isin(crossed_tickers)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "adjusted_close",
            "sma_50",
            "sma_200",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_death_cross_recent(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 30,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """SMA50 crossed below SMA200 within the last N days."""
    crossed = con.execute(f"""
        WITH latest_dates AS (
            SELECT ticker, MAX(date) AS latest_date FROM technicals_daily GROUP BY ticker
        ),
        cross_events AS (
            SELECT t.ticker,
                   LAG(t.sma_50 - t.sma_200) OVER (PARTITION BY t.ticker ORDER BY t.date) AS prev_diff,
                   t.sma_50 - t.sma_200 AS curr_diff
            FROM technicals_daily t
            JOIN latest_dates ld ON t.ticker = ld.ticker
            WHERE t.date >= ld.latest_date - INTERVAL {lookback_days + 1} DAY
              AND t.sma_50 IS NOT NULL AND t.sma_200 IS NOT NULL
        )
        SELECT DISTINCT ticker FROM cross_events
        WHERE prev_diff > 0 AND curr_diff <= 0
        """).df()
    crossed_tickers = set(crossed["ticker"].tolist())

    df = _base_df(con)
    df = df[df["ticker"].isin(crossed_tickers)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "adjusted_close",
            "sma_50",
            "sma_200",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


# ---------------------------------------------------------------------------
# Momentum screens
# ---------------------------------------------------------------------------


def screen_rsi_oversold(
    con: duckdb.DuckDBPyConnection,
    *,
    threshold: float = 30.0,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """RSI14 < threshold (default 30)."""
    df = _base_df(con)
    df = df[df["rsi_14"].notna() & (df["rsi_14"] < threshold)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "rsi_14",
            "adjusted_close",
            "pct_from_52w_low",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_rsi_overbought(
    con: duckdb.DuckDBPyConnection,
    *,
    threshold: float = 70.0,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """RSI14 > threshold (default 70)."""
    df = _base_df(con)
    df = df[df["rsi_14"].notna() & (df["rsi_14"] > threshold)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "rsi_14",
            "adjusted_close",
            "pct_from_52w_high",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_macd_bullish_crossover(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 5,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """MACD crossed above signal line within the last N days."""
    crossed = con.execute(f"""
        WITH latest_dates AS (
            SELECT ticker, MAX(date) AS latest_date FROM technicals_daily GROUP BY ticker
        ),
        cross_events AS (
            SELECT t.ticker,
                   LAG(t.macd - t.macd_signal) OVER (PARTITION BY t.ticker ORDER BY t.date) AS prev_diff,
                   t.macd - t.macd_signal AS curr_diff
            FROM technicals_daily t
            JOIN latest_dates ld ON t.ticker = ld.ticker
            WHERE t.date >= ld.latest_date - INTERVAL {lookback_days + 1} DAY
              AND t.macd IS NOT NULL AND t.macd_signal IS NOT NULL
        )
        SELECT DISTINCT ticker FROM cross_events
        WHERE prev_diff < 0 AND curr_diff >= 0
        """).df()
    crossed_tickers = set(crossed["ticker"].tolist())

    df = _base_df(con)
    df = df[df["ticker"].isin(crossed_tickers)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "macd",
            "macd_signal",
            "macd_histogram",
            "rsi_14",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_macd_bearish_crossover(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 5,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """MACD crossed below signal line within the last N days."""
    crossed = con.execute(f"""
        WITH latest_dates AS (
            SELECT ticker, MAX(date) AS latest_date FROM technicals_daily GROUP BY ticker
        ),
        cross_events AS (
            SELECT t.ticker,
                   LAG(t.macd - t.macd_signal) OVER (PARTITION BY t.ticker ORDER BY t.date) AS prev_diff,
                   t.macd - t.macd_signal AS curr_diff
            FROM technicals_daily t
            JOIN latest_dates ld ON t.ticker = ld.ticker
            WHERE t.date >= ld.latest_date - INTERVAL {lookback_days + 1} DAY
              AND t.macd IS NOT NULL AND t.macd_signal IS NOT NULL
        )
        SELECT DISTINCT ticker FROM cross_events
        WHERE prev_diff > 0 AND curr_diff <= 0
        """).df()
    crossed_tickers = set(crossed["ticker"].tolist())

    df = _base_df(con)
    df = df[df["ticker"].isin(crossed_tickers)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "macd",
            "macd_signal",
            "macd_histogram",
            "rsi_14",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


# ---------------------------------------------------------------------------
# Position screens
# ---------------------------------------------------------------------------


def screen_near_52w_high(
    con: duckdb.DuckDBPyConnection,
    *,
    pct_threshold: float = 5.0,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Price within pct_threshold% of 52-week high."""
    df = _base_df(con)
    threshold = -pct_threshold / 100.0
    df = df[df["pct_from_52w_high"].notna() & (df["pct_from_52w_high"] >= threshold)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "adjusted_close",
            "pct_from_52w_high",
            "rsi_14",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_near_52w_low(
    con: duckdb.DuckDBPyConnection,
    *,
    pct_threshold: float = 5.0,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Price within pct_threshold% of 52-week low."""
    df = _base_df(con)
    threshold = pct_threshold / 100.0
    df = df[df["pct_from_52w_low"].notna() & (df["pct_from_52w_low"] <= threshold)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "adjusted_close",
            "pct_from_52w_low",
            "rsi_14",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


# ---------------------------------------------------------------------------
# Volatility / volume screens
# ---------------------------------------------------------------------------


def screen_bb_squeeze(
    con: duckdb.DuckDBPyConnection,
    *,
    percentile: float = 20.0,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """BB width below own 252-day Nth percentile (default 20th) — low volatility compression."""
    frac = percentile / 100.0
    squeezed = con.execute(f"""
        WITH latest_dates AS (
            SELECT ticker, MAX(date) AS latest_date FROM technicals_daily GROUP BY ticker
        ),
        thresholds AS (
            SELECT t.ticker,
                   PERCENTILE_CONT({frac:.4f}) WITHIN GROUP (ORDER BY t.bb_width) AS thresh
            FROM technicals_daily t
            JOIN latest_dates ld ON t.ticker = ld.ticker
            WHERE t.date >= ld.latest_date - INTERVAL 252 DAY
              AND t.bb_width IS NOT NULL
            GROUP BY t.ticker
        ),
        current_tech AS (
            SELECT t.ticker, t.bb_width
            FROM technicals_daily t
            JOIN latest_dates ld ON t.ticker = ld.ticker AND t.date = ld.latest_date
        )
        SELECT ct.ticker
        FROM current_tech ct
        JOIN thresholds th ON ct.ticker = th.ticker
        WHERE ct.bb_width IS NOT NULL AND ct.bb_width < th.thresh
        """).df()
    squeezed_tickers = set(squeezed["ticker"].tolist())

    df = _base_df(con)
    df = df[df["ticker"].isin(squeezed_tickers)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "bb_width",
            "adjusted_close",
            "rsi_14",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )


def screen_volume_spike(
    con: duckdb.DuckDBPyConnection,
    *,
    threshold: float = 2.0,
    min_mktcap_b: float | None = None,
    min_adtv_m: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """volume_ratio > threshold (default 2x the 50-day average volume)."""
    df = _base_df(con)
    df = df[df["volume_ratio"].notna() & (df["volume_ratio"] > threshold)]
    df = _apply_size_filter(df, min_mktcap_b, min_adtv_m)
    return _finish(
        df,
        display_filter,
        [
            "ticker",
            "name",
            "sector",
            "volume_ratio",
            "adjusted_close",
            "pct_from_52w_high",
            "rsi_14",
            "mktcap_b",
            "adtv_20d_m",
        ],
    )
