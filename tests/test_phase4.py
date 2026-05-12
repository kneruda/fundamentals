"""Phase 4: computed multiples and technicals."""

import math
from datetime import date
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
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    return db


# ---------------------------------------------------------------------------
# Helpers for synthetic data
# ---------------------------------------------------------------------------


def insert_earnings(con, rows):
    """rows: list of (ticker, fiscal_period_end, report_date, eps_actual)"""
    for ticker, fpe, rd, eps in rows:
        con.execute(
            "INSERT INTO earnings_events (ticker, fiscal_period_end, report_date, eps_actual)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (ticker, fiscal_period_end) DO UPDATE SET"
            "   report_date = excluded.report_date, eps_actual = excluded.eps_actual",
            [ticker, fpe, rd, eps],
        )


def insert_prices(con, rows):
    """rows: list of (ticker, date, adjusted_close)"""
    for ticker, dt, adj in rows:
        con.execute(
            "INSERT INTO prices_daily (ticker, date, adjusted_close, open, high, low, close, volume)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (ticker, date) DO UPDATE SET adjusted_close = excluded.adjusted_close",
            [ticker, dt, adj, adj, adj, adj, adj, 0],
        )


def insert_shares(con, ticker, period_end, shares):
    con.execute(
        "INSERT INTO shares_outstanding (ticker, period_end, shares) VALUES (?, ?, ?)"
        " ON CONFLICT (ticker, period_end) DO UPDATE SET shares = excluded.shares",
        [ticker, period_end, shares],
    )


def insert_income_stmt(con, ticker, fiscal_period_end, report_date, total_revenue, ebitda):
    con.execute(
        "INSERT INTO income_statement"
        " (ticker, fiscal_period_end, report_date, currency, total_revenue, ebitda)"
        " VALUES (?, ?, ?, 'USD', ?, ?)"
        " ON CONFLICT (ticker, fiscal_period_end) DO UPDATE SET"
        "   report_date = excluded.report_date,"
        "   total_revenue = excluded.total_revenue, ebitda = excluded.ebitda",
        [ticker, fiscal_period_end, report_date, total_revenue, ebitda],
    )


def insert_balance_sheet(
    con, ticker, fiscal_period_end, report_date, equity, shares, ltd, std, cash
):
    con.execute(
        "INSERT INTO balance_sheet"
        " (ticker, fiscal_period_end, report_date, currency,"
        "  total_stockholder_equity, common_stock_shares_outstanding,"
        "  long_term_debt_total, short_term_debt, cash_and_short_term_investments)"
        " VALUES (?, ?, ?, 'USD', ?, ?, ?, ?, ?)"
        " ON CONFLICT (ticker, fiscal_period_end) DO UPDATE SET"
        "   report_date = excluded.report_date,"
        "   total_stockholder_equity = excluded.total_stockholder_equity,"
        "   common_stock_shares_outstanding = excluded.common_stock_shares_outstanding,"
        "   long_term_debt_total = excluded.long_term_debt_total,"
        "   short_term_debt = excluded.short_term_debt,"
        "   cash_and_short_term_investments = excluded.cash_and_short_term_investments",
        [ticker, fiscal_period_end, report_date, equity, shares, ltd, std, cash],
    )


def insert_cashflow(con, ticker, fiscal_period_end, report_date, fcf):
    con.execute(
        "INSERT INTO cash_flow"
        " (ticker, fiscal_period_end, report_date, currency, free_cash_flow)"
        " VALUES (?, ?, ?, 'USD', ?)"
        " ON CONFLICT (ticker, fiscal_period_end) DO UPDATE SET"
        "   report_date = excluded.report_date, free_cash_flow = excluded.free_cash_flow",
        [ticker, fiscal_period_end, report_date, fcf],
    )


# ---------------------------------------------------------------------------
# Views exist
# ---------------------------------------------------------------------------


def test_views_exist(db):
    views = {
        r[0]
        for r in db.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema='main'"
        ).fetchall()
    }
    for v in (
        "ttm_eps",
        "ttm_revenue",
        "ttm_ebitda",
        "ttm_fcf",
        "trailing_multiples_daily",
        "technicals_daily",
    ):
        assert v in views, f"missing view: {v}"


# ---------------------------------------------------------------------------
# TTM EPS — correctness and point-in-time
# ---------------------------------------------------------------------------


def test_ttm_eps_requires_four_quarters(db):
    """Only rows with exactly 4 quarters of actuals appear in ttm_eps."""
    insert_earnings(
        db,
        [
            ("T", "2023-03-31", "2023-04-28", 1.0),
            ("T", "2023-06-30", "2023-07-28", 1.2),
            ("T", "2023-09-30", "2023-10-27", 1.1),
        ],
    )
    rows = db.execute("SELECT * FROM ttm_eps WHERE ticker='T'").fetchall()
    assert rows == [], "expected no TTM rows with only 3 quarters"


def test_ttm_eps_value(db):
    """TTM EPS is the rolling 4-quarter sum of eps_actual."""
    insert_earnings(
        db,
        [
            ("T", "2023-03-31", "2023-04-28", 1.0),
            ("T", "2023-06-30", "2023-07-28", 1.2),
            ("T", "2023-09-30", "2023-10-27", 1.1),
            ("T", "2023-12-31", "2024-02-01", 2.0),  # TTM = 5.30
            ("T", "2024-03-31", "2024-04-26", 1.5),  # TTM = 5.80
        ],
    )
    rows = {
        r[0]: r[2]
        for r in db.execute(
            "SELECT report_date, ticker, ttm_eps FROM ttm_eps WHERE ticker='T' ORDER BY report_date"
        ).fetchall()
    }
    assert math.isclose(rows[date(2024, 2, 1)], 5.30, rel_tol=1e-9)
    assert math.isclose(rows[date(2024, 4, 26)], 5.80, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Point-in-time P/E integrity (most important test in the project)
# ---------------------------------------------------------------------------


def test_pe_uses_prior_ttm_before_report_date(db):
    """Price on day before earnings uses old TTM EPS; on report date uses new."""
    insert_earnings(
        db,
        [
            ("T", "2023-03-31", "2023-04-28", 1.0),
            ("T", "2023-06-30", "2023-07-28", 1.2),
            ("T", "2023-09-30", "2023-10-27", 1.1),
            ("T", "2023-12-31", "2024-02-01", 2.0),  # TTM1 = 5.30
            ("T", "2024-03-31", "2024-04-26", 1.5),  # TTM2 = 5.80
        ],
    )
    insert_shares(db, "T", "2024-01-01", 1_000_000)
    insert_prices(
        db,
        [
            ("T", "2024-04-25", 100.0),  # day before new earnings
            ("T", "2024-04-26", 100.0),  # report date for Q1 2024
        ],
    )

    rows = {
        r[0]: r[1]
        for r in db.execute(
            "SELECT date, pe_trailing FROM trailing_multiples_daily WHERE ticker='T' ORDER BY date"
        ).fetchall()
    }

    assert math.isclose(
        rows[date(2024, 4, 25)], 100.0 / 5.30, rel_tol=1e-6
    ), "day before earnings should use prior TTM EPS (5.30)"
    assert math.isclose(
        rows[date(2024, 4, 26)], 100.0 / 5.80, rel_tol=1e-6
    ), "report date should use new TTM EPS (5.80)"


def test_pe_null_for_negative_eps(db):
    """Tickers with negative TTM EPS produce NULL P/E, not a meaningless negative value."""
    insert_earnings(
        db,
        [
            ("LOSS", "2023-03-31", "2023-04-28", -0.5),
            ("LOSS", "2023-06-30", "2023-07-28", -0.8),
            ("LOSS", "2023-09-30", "2023-10-27", -0.6),
            ("LOSS", "2023-12-31", "2024-02-01", -0.9),  # TTM = -2.80 (negative)
        ],
    )
    insert_shares(db, "LOSS", "2024-01-01", 1_000_000)
    insert_prices(db, [("LOSS", "2024-02-02", 20.0)])

    row = db.execute(
        "SELECT pe_trailing FROM trailing_multiples_daily WHERE ticker='LOSS' AND date='2024-02-02'"
    ).fetchone()
    assert row is not None
    assert row[0] is None, "negative TTM EPS should yield NULL P/E"


def test_pe_null_for_zero_eps(db):
    """Zero TTM EPS yields NULL P/E (not division-by-zero or inf)."""
    insert_earnings(
        db,
        [
            ("ZERO", "2023-03-31", "2023-04-28", 0.0),
            ("ZERO", "2023-06-30", "2023-07-28", 0.0),
            ("ZERO", "2023-09-30", "2023-10-27", 0.0),
            ("ZERO", "2023-12-31", "2024-02-01", 0.0),
        ],
    )
    insert_shares(db, "ZERO", "2024-01-01", 1_000_000)
    insert_prices(db, [("ZERO", "2024-02-02", 10.0)])

    row = db.execute(
        "SELECT pe_trailing FROM trailing_multiples_daily WHERE ticker='ZERO' AND date='2024-02-02'"
    ).fetchone()
    assert row is not None
    assert row[0] is None


# ---------------------------------------------------------------------------
# P/S trailing
# ---------------------------------------------------------------------------


def test_ps_trailing(db):
    """P/S = market cap / TTM revenue."""
    insert_earnings(
        db,
        [
            ("T", "2023-03-31", "2023-04-28", 1.0),
            ("T", "2023-06-30", "2023-07-28", 1.0),
            ("T", "2023-09-30", "2023-10-27", 1.0),
            ("T", "2023-12-31", "2024-02-01", 1.0),
        ],
    )
    insert_income_stmt(db, "T", "2023-03-31", "2023-04-28", 100e9, 20e9)
    insert_income_stmt(db, "T", "2023-06-30", "2023-07-28", 110e9, 22e9)
    insert_income_stmt(db, "T", "2023-09-30", "2023-10-27", 105e9, 21e9)
    insert_income_stmt(db, "T", "2023-12-31", "2024-02-01", 120e9, 25e9)  # TTM rev = 435e9
    insert_shares(db, "T", "2024-01-01", 1_000_000)
    insert_prices(db, [("T", "2024-02-02", 100.0)])

    row = db.execute(
        "SELECT ps_trailing FROM trailing_multiples_daily WHERE ticker='T' AND date='2024-02-02'"
    ).fetchone()
    assert row is not None
    expected_ps = (100.0 * 1_000_000) / 435e9
    assert math.isclose(row[0], expected_ps, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# P/B trailing
# ---------------------------------------------------------------------------


def test_pb_trailing(db):
    """P/B = price / book_value_per_share where bvps = equity / shares."""
    insert_balance_sheet(db, "T", "2023-12-31", "2024-02-01", 50e9, 1_000_000, 10e9, 2e9, 5e9)
    insert_shares(db, "T", "2024-01-01", 1_000_000)
    insert_prices(db, [("T", "2024-02-02", 100.0)])

    row = db.execute(
        "SELECT pb_trailing FROM trailing_multiples_daily WHERE ticker='T' AND date='2024-02-02'"
    ).fetchone()
    assert row is not None
    bvps = 50e9 / 1_000_000
    assert math.isclose(row[0], 100.0 / bvps, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# EV/EBITDA trailing
# ---------------------------------------------------------------------------


def test_ev_ebitda_trailing(db):
    """EV/EBITDA = (mktcap + ltd + std - cash) / ttm_ebitda."""
    insert_income_stmt(db, "T", "2023-03-31", "2023-04-28", 100e9, 10e9)
    insert_income_stmt(db, "T", "2023-06-30", "2023-07-28", 100e9, 11e9)
    insert_income_stmt(db, "T", "2023-09-30", "2023-10-27", 100e9, 12e9)
    insert_income_stmt(db, "T", "2023-12-31", "2024-02-01", 100e9, 13e9)  # TTM EBITDA = 46e9
    insert_earnings(
        db,
        [
            ("T", "2023-03-31", "2023-04-28", None),
            ("T", "2023-06-30", "2023-07-28", None),
            ("T", "2023-09-30", "2023-10-27", None),
            ("T", "2023-12-31", "2024-02-01", None),
        ],
    )
    insert_balance_sheet(db, "T", "2023-12-31", "2024-02-01", 50e9, 1_000_000, 20e9, 5e9, 10e9)
    insert_shares(db, "T", "2024-01-01", 1_000_000)
    insert_prices(db, [("T", "2024-02-02", 100.0)])

    row = db.execute(
        "SELECT ev_ebitda_trailing FROM trailing_multiples_daily WHERE ticker='T' AND date='2024-02-02'"
    ).fetchone()
    assert row is not None
    mktcap = 100.0 * 1_000_000
    ev = mktcap + 20e9 + 5e9 - 10e9
    expected = ev / 46e9
    assert math.isclose(row[0], expected, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# FCF yield
# ---------------------------------------------------------------------------


def test_fcf_yield(db):
    """FCF yield = TTM FCF / mktcap."""
    insert_cashflow(db, "T", "2023-03-31", "2023-04-28", 5e9)
    insert_cashflow(db, "T", "2023-06-30", "2023-07-28", 6e9)
    insert_cashflow(db, "T", "2023-09-30", "2023-10-27", 5e9)
    insert_cashflow(db, "T", "2023-12-31", "2024-02-01", 7e9)  # TTM FCF = 23e9
    insert_earnings(
        db,
        [
            ("T", "2023-03-31", "2023-04-28", None),
            ("T", "2023-06-30", "2023-07-28", None),
            ("T", "2023-09-30", "2023-10-27", None),
            ("T", "2023-12-31", "2024-02-01", None),
        ],
    )
    insert_shares(db, "T", "2024-01-01", 1_000_000)
    insert_prices(db, [("T", "2024-02-02", 100.0)])

    row = db.execute(
        "SELECT fcf_yield FROM trailing_multiples_daily WHERE ticker='T' AND date='2024-02-02'"
    ).fetchone()
    assert row is not None
    expected = 23e9 / (100.0 * 1_000_000)
    assert math.isclose(row[0], expected, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# No look-ahead across AAPL's 2020-08-31 split
# ---------------------------------------------------------------------------


def test_aapl_split_no_discontinuity(loaded_db):
    """Trailing P/E shows no discontinuity across AAPL's 2020-08-31 split.

    Both price series and EPS are on the same split-adjusted basis so the multiple
    should move smoothly. We verify the ratio doesn't jump by more than a small
    threshold around the split date.
    """
    rows = loaded_db.execute("""
        SELECT date, pe_trailing
        FROM trailing_multiples_daily
        WHERE ticker = 'AAPL'
          AND date BETWEEN '2020-08-25' AND '2020-09-04'
          AND pe_trailing IS NOT NULL
        ORDER BY date
    """).fetchall()

    # Need at least 2 rows spanning the split date
    assert len(rows) >= 2, "expected price rows around the AAPL split date"

    split_date = date(2020, 8, 31)
    pre = [r[1] for r in rows if r[0] < split_date]
    post = [r[1] for r in rows if r[0] >= split_date]

    if pre and post:
        # The ratio between the last pre-split PE and first post-split PE should
        # not be close to 4x (which would indicate un-adjusted prices used).
        ratio = post[0] / pre[-1]
        assert 0.75 < ratio < 1.33, f"P/E ratio across split suggests mis-adjustment: {ratio:.2f}"


# ---------------------------------------------------------------------------
# Technicals — moving averages
# ---------------------------------------------------------------------------


def test_ma_20_value(db):
    """20-day MA is the mean of the last 20 adjusted_close values."""
    prices = [(date(2024, 1, i + 1), float(i + 1)) for i in range(25)]
    for dt, p in prices:
        insert_prices(db, [("T", dt, p)])

    row = db.execute(
        "SELECT date, ma_20 FROM technicals_daily WHERE ticker='T' AND date='2024-01-25'"
    ).fetchone()
    assert row is not None
    expected = sum(i + 1 for i in range(5, 25)) / 20.0  # days 6..25
    assert math.isclose(row[1], expected, rel_tol=1e-9)


def test_technicals_52w_range(db):
    """52-week high and low reflect the rolling 252-row window."""
    prices = [(date(2024, 1, 1), 100.0), (date(2024, 6, 1), 150.0), (date(2024, 12, 31), 80.0)]
    for dt, p in prices:
        insert_prices(db, [("T", dt, p)])

    row = db.execute(
        "SELECT high_52w, low_52w FROM technicals_daily WHERE ticker='T' AND date='2024-12-31'"
    ).fetchone()
    assert row is not None
    # Only 3 rows — all within the 252-row window
    assert math.isclose(row[0], 150.0)  # high
    assert math.isclose(row[1], 80.0)  # low


def test_beta_null_without_spy(db):
    """beta_spy_252d is NULL when SPY is not in prices_daily."""
    prices = [(date(2024, 1, i + 1), float(100 + i)) for i in range(10)]
    for dt, p in prices:
        insert_prices(db, [("T", dt, p)])

    rows = db.execute("SELECT beta_spy_252d FROM technicals_daily WHERE ticker='T'").fetchall()
    assert all(
        r[0] is None or math.isnan(r[0]) for r in rows
    ), "beta should be NULL/NaN when SPY has no price data"


def test_realized_vol_non_negative(db):
    """Realized volatility (annualized) is non-negative."""
    from datetime import timedelta

    start = date(2024, 1, 1)
    prices = [(start + timedelta(days=i), float(100 + (i % 5))) for i in range(70)]
    for dt, p in prices:
        insert_prices(db, [("T", dt, p)])

    rows = db.execute(
        "SELECT realized_vol_60d FROM technicals_daily WHERE ticker='T' AND realized_vol_60d IS NOT NULL"
    ).fetchall()
    assert rows, "expected some non-null volatility rows"
    assert all(r[0] >= 0 for r in rows)


# ---------------------------------------------------------------------------
# End-to-end: AAPL loads cleanly and produces multiples
# ---------------------------------------------------------------------------


def test_aapl_ttm_eps_populated(loaded_db):
    """TTM EPS view returns rows for AAPL after loading the fixture."""
    rows = loaded_db.execute("SELECT COUNT(*) FROM ttm_eps WHERE ticker='AAPL'").fetchone()[0]
    assert rows > 0


def test_aapl_trailing_multiples_populated(loaded_db):
    """Trailing multiples view returns rows for AAPL after loading fixture."""
    rows = loaded_db.execute(
        "SELECT COUNT(*) FROM trailing_multiples_daily WHERE ticker='AAPL' AND pe_trailing IS NOT NULL"
    ).fetchone()[0]
    assert rows > 0, "expected non-null P/E rows for AAPL"


def test_aapl_technicals_populated(loaded_db):
    """Technicals view returns MA rows for AAPL after loading price history."""
    rows = loaded_db.execute(
        "SELECT COUNT(*) FROM technicals_daily WHERE ticker='AAPL' AND ma_200 IS NOT NULL"
    ).fetchone()[0]
    assert rows > 0, "expected 200-day MA rows for AAPL"


# ---------------------------------------------------------------------------
# REVIEW.md fix: load_daily sources active tickers from universe table
# ---------------------------------------------------------------------------


def test_ingest_universe_uses_table_not_yaml(db, monkeypatch):
    """ingest_universe processes only active rows from the universe table."""
    db.execute("INSERT INTO universe (ticker, active) VALUES ('ACTIVE1', true)")
    db.execute("INSERT INTO universe (ticker, active) VALUES ('INACTIVE', false)")

    ingested = []

    from unittest.mock import patch

    def fake_fetch_and_ingest(con, ticker):
        ingested.append(ticker)

    with patch("src.ingest.orchestrator.fetch_and_ingest", side_effect=fake_fetch_and_ingest):
        from src.ingest.orchestrator import ingest_universe

        ingest_universe(db)

    assert "ACTIVE1" in ingested
    assert "INACTIVE" not in ingested
