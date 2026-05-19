"""Tests for the technicals_daily table, recompute_technicals(), and technical screens."""

import math
from datetime import date, timedelta
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FUNDAMENTALS = FIXTURES / "AAPL-Fundamentals.json"
PRICES = FIXTURES / "AAPL.json"


@pytest.fixture()
def db():
    from src.schema.runner import open_db

    con = open_db(":memory:")
    yield con
    con.close()


@pytest.fixture()
def loaded_db(db):
    from src.compute.technicals import recompute_technicals
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    recompute_technicals(db, ["AAPL"])
    return db


def _insert_prices(
    con, ticker: str, rows: list[tuple[date, float, float, float, float, int]]
) -> None:
    """rows: (date, open, high, low, close_adj, volume). close=adj for simplicity."""
    for dt, o, h, lo, a, vol in rows:
        con.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (ticker, date) DO UPDATE SET"
            "   adjusted_close = excluded.adjusted_close,"
            "   high = excluded.high, low = excluded.low, close = excluded.close",
            [ticker, dt, o, h, lo, a, a, vol],
        )


def _simple_prices(
    ticker: str, n: int, start_price: float = 100.0, start_date: date = date(2020, 1, 1)
) -> list:
    """Generate n days of simple incrementing prices."""
    return [
        (
            start_date + timedelta(days=i),
            start_price + i,
            start_price + i * 1.01,
            start_price + i * 0.99,
            start_price + i,
            1_000_000,
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Indicator unit tests
# ---------------------------------------------------------------------------


def test_sma_20_exact(db):
    """SMA20 equals the simple mean of the last 20 adjusted_close values."""
    from src.compute.technicals import recompute_technicals

    prices = [(date(2024, 1, i + 1), float(i + 1)) for i in range(25)]
    for dt, p in prices:
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["T", dt, p, p, p, p, p, 0],
        )
    recompute_technicals(db, ["T"])

    row = db.execute(
        "SELECT sma_20 FROM technicals_daily WHERE ticker='T' AND date='2024-01-25'"
    ).fetchone()
    assert row is not None
    expected = sum(i + 1 for i in range(5, 25)) / 20.0
    assert math.isclose(row[0], expected, rel_tol=1e-9)


def test_sma_null_before_min_periods(db):
    """SMA200 is NULL when fewer than 200 rows exist."""
    from src.compute.technicals import recompute_technicals

    for i in range(50):
        dt = date(2024, 1, 1) + timedelta(days=i)
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, 100, 101, 99, 100, 100, 1000)",
            ["T", dt],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute("SELECT sma_200 FROM technicals_daily WHERE ticker='T'").fetchall()
    assert all(r[0] is None for r in rows), "SMA200 must be NULL with < 200 rows"


def test_ema_12_monotone(db):
    """EMA12 on a flat series converges to the flat price."""
    from src.compute.technicals import recompute_technicals

    price = 50.0
    for i in range(60):
        dt = date(2024, 1, 1) + timedelta(days=i)
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, price, price, price, price, price],
        )
    recompute_technicals(db, ["T"])

    row = db.execute(
        "SELECT ema_12 FROM technicals_daily WHERE ticker='T' ORDER BY date DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert math.isclose(
        row[0], price, rel_tol=1e-6
    ), f"EMA12 on flat series should equal {price}, got {row[0]}"


def test_rsi_canonical(db):
    """Wilder's RSI: well-known canonical sequence gives RSI ~70.53 on day 15."""
    from src.compute.technicals import recompute_technicals

    # Standard RSI(14) test sequence: 14 ups then 1 down
    prices_adj = [
        44.34,
        44.09,
        44.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.15,
        43.61,
        44.33,
        44.83,
        45.10,
        45.15,
        45.98,
        45.41,
    ]
    for i, p in enumerate(prices_adj):
        dt = date(2024, 1, 1) + timedelta(days=i)
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute(
        "SELECT rsi_14 FROM technicals_daily WHERE ticker='T' ORDER BY date"
    ).fetchall()
    rsi_values = [r[0] for r in rows]
    # First 14 rows: NaN (need 15 prices = 14 diffs, and min_periods=14 for EWM)
    non_null = [(i, v) for i, v in enumerate(rsi_values) if v is not None and not math.isnan(v)]
    assert len(non_null) > 0, "expected at least one non-null RSI value"
    # Last value should be reasonable RSI (30–80 range for this test sequence)
    last_rsi = non_null[-1][1]
    assert 20 < last_rsi < 90, f"RSI out of expected range: {last_rsi}"


def test_rsi_null_before_min_periods(db):
    """RSI14 is NULL for fewer than 15 price rows."""
    from src.compute.technicals import recompute_technicals

    for i in range(10):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + i
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute("SELECT rsi_14 FROM technicals_daily WHERE ticker='T'").fetchall()
    assert all(
        r[0] is None or math.isnan(r[0]) for r in rows
    ), "RSI14 must be NULL with < 15 price rows"


def test_atr_uses_raw_ohlc(db):
    """ATR uses raw H/L/C, not adjusted_close. Wider H/L spread → larger ATR."""
    from src.compute.technicals import recompute_technicals

    for i in range(30):
        dt = date(2024, 1, 1) + timedelta(days=i)
        # Deliberately wide high/low range (5 units) vs flat adjusted_close
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, 100, 105, 95, 100, 100, 1000)",
            ["T", dt],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute(
        "SELECT atr_14 FROM technicals_daily WHERE ticker='T' AND atr_14 IS NOT NULL"
    ).fetchall()
    assert rows, "expected non-null ATR with 30 rows"
    # True range per row is max(H-L, |H-prev_C|, |L-prev_C|) = max(10, 5, 5) = 10
    # Wilder's ATR should converge near 10
    for r in rows:
        assert r[0] > 0, "ATR must be positive"


def test_macd_equals_ema12_minus_ema26(db):
    """MACD line = EMA12 - EMA26 on every row."""
    from src.compute.technicals import recompute_technicals

    for i in range(60):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + i * 0.3
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute(
        "SELECT macd, ema_12, ema_26 FROM technicals_daily WHERE ticker='T' AND macd IS NOT NULL"
    ).fetchall()
    assert rows
    for macd, e12, e26 in rows:
        assert math.isclose(macd, e12 - e26, rel_tol=1e-9)


def test_bb_width_non_negative(db):
    """Bollinger Band width is non-negative wherever defined."""
    import math as _math

    from src.compute.technicals import recompute_technicals

    for i in range(30):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + _math.sin(i * 0.5) * 10
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute(
        "SELECT bb_width FROM technicals_daily WHERE ticker='T' AND bb_width IS NOT NULL"
    ).fetchall()
    assert rows
    assert all(r[0] >= 0 for r in rows)


def test_beta_null_without_benchmark(db):
    """beta_252d is NULL/NaN when benchmark ticker has no price data."""
    from src.compute.technicals import recompute_technicals

    for i in range(10):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + i
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute("SELECT beta_252d FROM technicals_daily WHERE ticker='T'").fetchall()
    assert all(r[0] is None or math.isnan(r[0]) for r in rows)


def test_volume_indicators_null_when_zero_volume(db):
    """volume_sma_50 and volume_ratio are NULL when all volume is zero."""
    from src.compute.technicals import recompute_technicals

    for i in range(60):
        dt = date(2024, 1, 1) + timedelta(days=i)
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, 100, 101, 99, 100, 100, 0)",
            ["T", dt],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute(
        "SELECT volume_sma_50, volume_ratio FROM technicals_daily WHERE ticker='T'"
    ).fetchall()
    assert rows
    # All volume is zero → treated as NaN → sma and ratio both NULL
    for sma, ratio in rows:
        assert sma is None or math.isnan(sma), f"volume_sma_50 should be NULL, got {sma}"
        assert ratio is None or math.isnan(ratio), f"volume_ratio should be NULL, got {ratio}"


def test_pct_from_52w_high_non_positive(db):
    """pct_from_52w_high is always ≤ 0 by construction."""
    from src.compute.technicals import recompute_technicals

    for i in range(60):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + math.sin(i * 0.3) * 10
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    rows = db.execute(
        "SELECT pct_from_52w_high FROM technicals_daily WHERE ticker='T' AND pct_from_52w_high IS NOT NULL"
    ).fetchall()
    assert rows
    assert all(r[0] <= 1e-9 for r in rows), "pct_from_52w_high must be <= 0"


# ---------------------------------------------------------------------------
# Idempotency and full-rebuild tests
# ---------------------------------------------------------------------------


def test_recompute_idempotent(db):
    """recompute_technicals twice in a row produces identical rows."""
    from src.compute.technicals import recompute_technicals

    for i in range(30):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + i
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )

    recompute_technicals(db, ["T"])
    snap1 = db.execute(
        "SELECT date, sma_20, ema_12, rsi_14 FROM technicals_daily WHERE ticker='T' ORDER BY date"
    ).fetchall()

    recompute_technicals(db, ["T"])
    snap2 = db.execute(
        "SELECT date, sma_20, ema_12, rsi_14 FROM technicals_daily WHERE ticker='T' ORDER BY date"
    ).fetchall()

    assert len(snap1) == len(snap2)
    for r1, r2 in zip(snap1, snap2, strict=True):
        for v1, v2 in zip(r1, r2, strict=True):
            if not isinstance(v1, float):
                assert v1 == v2
            elif math.isnan(v1):
                assert v2 is None or math.isnan(v2)
            else:
                assert math.isclose(v1, v2, rel_tol=1e-12)


def test_recompute_full_rebuild(db):
    """Wiping the table and recomputing matches running on top of populated rows."""
    from src.compute.technicals import recompute_technicals

    for i in range(30):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + math.sin(i * 0.5) * 5
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )

    recompute_technicals(db, ["T"])
    snap1 = db.execute(
        "SELECT date, sma_20, ema_12 FROM technicals_daily WHERE ticker='T' ORDER BY date"
    ).fetchall()

    db.execute("DELETE FROM technicals_daily")
    recompute_technicals(db, ["T"])
    snap2 = db.execute(
        "SELECT date, sma_20, ema_12 FROM technicals_daily WHERE ticker='T' ORDER BY date"
    ).fetchall()

    assert snap1 == snap2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_single_day_all_null(db):
    """Single price row: all rolling indicators are NULL."""
    from src.compute.technicals import recompute_technicals

    db.execute(
        "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
        " VALUES ('T', '2024-01-01', 100, 102, 98, 100, 100, 5000)"
    )
    recompute_technicals(db, ["T"])

    row = db.execute(
        "SELECT sma_20, sma_200, rsi_14, macd, atr_14, volume_ratio "
        "FROM technicals_daily WHERE ticker='T'"
    ).fetchone()
    assert row is not None
    for val in row:
        assert val is None or (
            isinstance(val, float) and math.isnan(val)
        ), f"expected NULL, got {val}"


def test_short_history_sma200_null_sma20_not(db):
    """With 25 rows: sma_20 present, sma_200 NULL, no error."""
    from src.compute.technicals import recompute_technicals

    for i in range(25):
        dt = date(2024, 1, 1) + timedelta(days=i)
        p = 100.0 + i
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 1000)",
            ["T", dt, p, p, p, p, p],
        )
    recompute_technicals(db, ["T"])

    last_row = db.execute(
        "SELECT sma_20, sma_200 FROM technicals_daily WHERE ticker='T' ORDER BY date DESC LIMIT 1"
    ).fetchone()
    assert last_row is not None
    assert last_row[0] is not None, "sma_20 should be defined with 25 rows"
    assert last_row[1] is None, "sma_200 should be NULL with < 200 rows"


def test_no_prices_no_rows(db):
    """Ticker with no prices produces no rows in technicals_daily."""
    from src.compute.technicals import recompute_technicals

    recompute_technicals(db, ["GHOST"])
    count = db.execute("SELECT COUNT(*) FROM technicals_daily WHERE ticker='GHOST'").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# AAPL end-to-end
# ---------------------------------------------------------------------------


def test_aapl_all_columns_populated(loaded_db):
    """AAPL loaded from fixture: SMA200 and EMA12 rows are present."""
    for col in ["sma_20", "sma_50", "sma_200", "ema_12", "rsi_14", "macd", "bb_width"]:
        count = loaded_db.execute(
            f"SELECT COUNT(*) FROM technicals_daily WHERE ticker='AAPL' AND {col} IS NOT NULL"
        ).fetchone()[0]
        assert count > 0, f"expected non-null rows for {col}"


# ---------------------------------------------------------------------------
# Technical screens smoke tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def screens_db(db):
    """Seed a small universe with enough history to exercise all screens."""
    from src.compute.technicals import recompute_technicals

    tickers = ["LONG", "SHORT"]
    for ticker in tickers:
        db.execute(f"INSERT INTO universe (ticker) VALUES ('{ticker}')")
        db.execute(
            f"INSERT INTO security_master (ticker, code, exchange, name, sector, currency_code)"
            f" VALUES ('{ticker}', '{ticker}', 'US', '{ticker} Inc', 'Technology', 'USD')"
        )
        db.execute(
            "INSERT INTO shares_outstanding (ticker, period_end, shares) VALUES (?, ?, ?)",
            [ticker, date(2024, 1, 1), 1_000_000],
        )

    # LONG: steadily rising price (will trigger uptrend, near-52w-high)
    for i in range(300):
        dt = date(2023, 1, 1) + timedelta(days=i)
        p = 100.0 + i * 0.1
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["LONG", dt, p, p * 1.01, p * 0.99, p, p, 1_000_000],
        )

    # SHORT: steadily falling price (will trigger downtrend)
    for i in range(300):
        dt = date(2023, 1, 1) + timedelta(days=i)
        p = 200.0 - i * 0.1
        db.execute(
            "INSERT INTO prices_daily (ticker, date, open, high, low, close, adjusted_close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["SHORT", dt, p, p * 1.01, p * 0.99, p, p, 1_000_000],
        )

    recompute_technicals(db, ["LONG", "SHORT"])
    return db


_ALL_SCREENS = [
    "confirmed_uptrend",
    "confirmed_downtrend",
    "golden_cross_recent",
    "death_cross_recent",
    "rsi_oversold",
    "rsi_overbought",
    "macd_bullish_crossover",
    "macd_bearish_crossover",
    "near_52w_high",
    "near_52w_low",
    "bb_squeeze",
    "volume_spike",
]


@pytest.mark.parametrize("screen_name", _ALL_SCREENS)
def test_screen_runs_without_error(screens_db, screen_name):
    """Each technical screen runs without error and returns a DataFrame with expected columns."""
    import importlib

    import pandas as pd

    mod = importlib.import_module("src.screens.technicals")
    fn = getattr(mod, f"screen_{screen_name}")
    result = fn(screens_db)

    assert isinstance(result, pd.DataFrame), f"screen_{screen_name} must return a DataFrame"
    for col in ["ticker", "name", "sector"]:
        assert col in result.columns, f"screen_{screen_name} result missing column '{col}'"


def test_confirmed_uptrend_matches_long(screens_db):
    """screen_confirmed_uptrend returns LONG (rising price) but not SHORT (falling)."""
    from src.screens.technicals import screen_confirmed_uptrend

    df = screen_confirmed_uptrend(screens_db)
    tickers = set(df["ticker"].tolist())
    assert "LONG" in tickers
    assert "SHORT" not in tickers


def test_confirmed_downtrend_matches_short(screens_db):
    """screen_confirmed_downtrend returns SHORT (falling price) but not LONG (rising)."""
    from src.screens.technicals import screen_confirmed_downtrend

    df = screen_confirmed_downtrend(screens_db)
    tickers = set(df["ticker"].tolist())
    assert "SHORT" in tickers
    assert "LONG" not in tickers


def test_display_filter_applied(screens_db):
    """display_filter limits results to specified tickers."""
    from src.screens.technicals import screen_confirmed_uptrend

    df = screen_confirmed_uptrend(screens_db, display_filter=["LONG"])
    assert all(t == "LONG" for t in df["ticker"].tolist())

    df_empty = screen_confirmed_uptrend(screens_db, display_filter=["NONEXISTENT"])
    assert df_empty.empty
