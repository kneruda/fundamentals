"""Compute and persist technical indicators for all active tickers.

All indicators are written to the `technicals_daily` table (created by
migration 007). The function is fully idempotent: it deletes existing rows
for each ticker before inserting, so re-running produces identical results.

Price source: adjusted_close for all indicators except ATR (raw H/L/C).
EMA warm-up: ewm(adjust=False) — recursive first-value seed, matches TradingView.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yml"

_OUTPUT_COLS = [
    "ticker",
    "date",
    "adjusted_close",
    "sma_20",
    "sma_50",
    "sma_200",
    "high_52w",
    "low_52w",
    "realized_vol_60d",
    "beta_252d",
    "ema_12",
    "ema_26",
    "ema_50",
    "pct_from_sma_50",
    "pct_from_sma_200",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_middle",
    "bb_upper",
    "bb_lower",
    "bb_width",
    "atr_14",
    "volume_sma_50",
    "volume_ratio",
    "pct_from_52w_high",
    "pct_from_52w_low",
]


def _benchmark_ticker() -> str:
    with _SETTINGS_PATH.open() as f:
        cfg = yaml.safe_load(f)
    return cfg.get("benchmark", {}).get("ticker", "SPY.US")


def _wilder_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    alpha = 1.0 / period
    avg_gain = gain.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    # avg_loss=0 with avg_gain>0 → rs=inf → RSI=100 (pandas handles inf correctly)
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    alpha = 1.0 / period
    return tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def _compute_indicators(df: pd.DataFrame, bm_log_ret: pd.Series | None) -> pd.DataFrame:
    """Add all technical indicator columns to df (in-place). Returns df."""
    ac = df["adjusted_close"]

    df["sma_20"] = ac.rolling(20, min_periods=20).mean()
    df["sma_50"] = ac.rolling(50, min_periods=50).mean()
    df["sma_200"] = ac.rolling(200, min_periods=200).mean()
    df["high_52w"] = ac.rolling(252, min_periods=1).max()
    df["low_52w"] = ac.rolling(252, min_periods=1).min()

    log_ret = np.log(ac / ac.shift(1))
    df["realized_vol_60d"] = log_ret.rolling(60, min_periods=60).std() * np.sqrt(252)

    if bm_log_ret is not None:
        dated = pd.Series(log_ret.values, index=pd.to_datetime(df["date"]))
        aligned_bm = bm_log_ret.reindex(dated.index)
        cov = dated.rolling(252, min_periods=252).cov(aligned_bm)
        var = aligned_bm.rolling(252, min_periods=252).var()
        df["beta_252d"] = (cov / var.replace(0.0, np.nan)).values
    else:
        df["beta_252d"] = np.nan

    df["ema_12"] = ac.ewm(span=12, adjust=False, min_periods=12).mean()
    df["ema_26"] = ac.ewm(span=26, adjust=False, min_periods=26).mean()
    df["ema_50"] = ac.ewm(span=50, adjust=False, min_periods=50).mean()

    df["pct_from_sma_50"] = (ac - df["sma_50"]) / df["sma_50"]
    df["pct_from_sma_200"] = (ac - df["sma_200"]) / df["sma_200"]

    df["rsi_14"] = _wilder_rsi(ac, 14)

    df["macd"] = df["ema_12"] - df["ema_26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    df["macd_histogram"] = df["macd"] - df["macd_signal"]

    df["bb_middle"] = df["sma_20"]
    std_20 = ac.rolling(20, min_periods=20).std()
    df["bb_upper"] = df["bb_middle"] + 2.0 * std_20
    df["bb_lower"] = df["bb_middle"] - 2.0 * std_20
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

    df["atr_14"] = _wilder_atr(df["high"], df["low"], df["close"], 14)

    vol = df["volume"].astype(float).replace(0.0, np.nan)
    df["volume_sma_50"] = vol.rolling(50, min_periods=50).mean()
    df["volume_ratio"] = vol / df["volume_sma_50"]

    df["pct_from_52w_high"] = (ac - df["high_52w"]) / df["high_52w"]
    df["pct_from_52w_low"] = (ac - df["low_52w"]) / df["low_52w"]

    return df


def recompute_technicals(
    con: duckdb.DuckDBPyConnection,
    tickers: list[str] | None = None,
) -> None:
    """Recompute and persist technicals for one ticker or the full active universe.

    Deletes existing rows for each ticker before inserting so the function
    is fully idempotent. tickers=None means all active tickers.
    """
    if tickers is None:
        tickers = [r[0] for r in con.execute("SELECT ticker FROM universe WHERE active").fetchall()]

    benchmark = _benchmark_ticker()

    bm_prices = con.execute(
        "SELECT date, adjusted_close FROM prices_daily WHERE ticker = ? ORDER BY date",
        [benchmark],
    ).df()
    if not bm_prices.empty:
        bm_prices = bm_prices.set_index("date")["adjusted_close"]
        bm_prices.index = pd.to_datetime(bm_prices.index)
        bm_log_ret = np.log(bm_prices / bm_prices.shift(1))
    else:
        bm_log_ret = None

    for ticker in tickers:
        if ticker == benchmark:
            continue

        df = con.execute(
            "SELECT date, open, high, low, close, adjusted_close, volume "
            "FROM prices_daily WHERE ticker = ? ORDER BY date",
            [ticker],
        ).df()

        if df.empty:
            continue

        df = df.sort_values("date").reset_index(drop=True)

        _compute_indicators(df, bm_log_ret)

        df["ticker"] = ticker

        to_insert = df[_OUTPUT_COLS].copy()  # noqa: F841 — referenced by name in DuckDB SQL below

        cols_sql = ", ".join(_OUTPUT_COLS)
        con.execute("DELETE FROM technicals_daily WHERE ticker = ?", [ticker])
        con.execute(f"INSERT INTO technicals_daily ({cols_sql}) SELECT * FROM to_insert")
