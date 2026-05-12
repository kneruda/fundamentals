"""Phase 7: trailing screens — smoke tests and math spot-checks."""

from pathlib import Path

import pandas as pd
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
    db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    return db


# ---------------------------------------------------------------------------
# Absolute valuation
# ---------------------------------------------------------------------------


def test_absolute_valuation_returns_dataframe(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    df = screen_absolute_valuation(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "ticker" in df.columns
    assert "pe_trailing" in df.columns


def test_absolute_valuation_aapl_present_no_filter(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    df = screen_absolute_valuation(loaded_db)
    assert "AAPL" in df["ticker"].values


def test_absolute_valuation_pe_filter_excludes(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    # AAPL trailing P/E is ~35; max_pe=5 should exclude it
    df = screen_absolute_valuation(loaded_db, max_pe=5.0)
    assert "AAPL" not in df["ticker"].values


def test_absolute_valuation_fcf_yield_filter_includes(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    # AAPL FCF yield is ~2.99%; min 1% should include it
    df = screen_absolute_valuation(loaded_db, min_fcf_yield=1.0)
    assert "AAPL" in df["ticker"].values


def test_absolute_valuation_fcf_yield_filter_excludes(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    # min 50% FCF yield is impossible; AAPL excluded
    df = screen_absolute_valuation(loaded_db, min_fcf_yield=50.0)
    assert "AAPL" not in df["ticker"].values


# ---------------------------------------------------------------------------
# Relative history
# ---------------------------------------------------------------------------


def test_relative_history_returns_dataframe(loaded_db):
    from src.screens.trailing import screen_relative_history

    df = screen_relative_history(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "pe_pct_rank" in df.columns
    assert "ev_pct_rank" in df.columns


def test_relative_history_rank_bounds(loaded_db):
    """Percentile ranks must be in [0, 100]."""
    from src.screens.trailing import screen_relative_history

    df = screen_relative_history(loaded_db)
    for col in ["pe_pct_rank", "ev_pct_rank", "ps_pct_rank"]:
        vals = df[col].dropna()
        if len(vals):
            assert vals.min() >= 0.0
            assert vals.max() <= 100.0


def test_relative_history_pe_rank_filter_excludes(loaded_db):
    from src.screens.trailing import screen_relative_history

    # AAPL is the only ticker; its rank is 100 (it is at its 5y high or close).
    # Setting max_pe_rank=0 should exclude everything.
    df = screen_relative_history(loaded_db, max_pe_rank=0.0)
    assert df.empty


# ---------------------------------------------------------------------------
# Growth
# ---------------------------------------------------------------------------


def test_growth_returns_dataframe(loaded_db):
    from src.screens.trailing import screen_growth

    df = screen_growth(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "rev_yoy_pct" in df.columns
    assert "is_accelerating" in df.columns


def test_growth_impossible_threshold_excludes(loaded_db):
    from src.screens.trailing import screen_growth

    # No company has 1000% revenue YoY growth
    df = screen_growth(loaded_db, min_rev_yoy=1000.0)
    assert df.empty


def test_growth_acceleration_column_is_bool(loaded_db):
    from src.screens.trailing import screen_growth

    df = screen_growth(loaded_db)
    row = df[df["ticker"] == "AAPL"]
    if not row.empty:
        assert row["is_accelerating"].iloc[0] in (True, False)


# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------


def test_quality_returns_dataframe(loaded_db):
    from src.screens.trailing import screen_quality

    df = screen_quality(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "roe_pct" in df.columns
    assert "roic_pct" in df.columns
    assert "fcf_conversion_pct" in df.columns


def test_quality_aapl_roe_is_high(loaded_db):
    from src.screens.trailing import screen_quality

    df = screen_quality(loaded_db)
    row = df[df["ticker"] == "AAPL"]
    assert not row.empty
    roe = row["roe_pct"].iloc[0]
    # AAPL return_on_equity_ttm fixture is ~1.4147 => 141.47%
    assert roe == pytest.approx(141.47, abs=5.0)


def test_quality_roe_filter_includes(loaded_db):
    from src.screens.trailing import screen_quality

    # AAPL ROE ~141%; min 100% should still include it
    df = screen_quality(loaded_db, min_roe=100.0)
    assert "AAPL" in df["ticker"].values


def test_quality_roe_filter_excludes(loaded_db):
    from src.screens.trailing import screen_quality

    # min 1000% ROE is impossible
    df = screen_quality(loaded_db, min_roe=1000.0)
    assert df.empty


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------


def test_balance_sheet_returns_dataframe(loaded_db):
    from src.screens.trailing import screen_balance_sheet

    df = screen_balance_sheet(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "net_debt_ebitda" in df.columns
    assert "current_ratio" in df.columns


def test_balance_sheet_current_ratio_is_positive(loaded_db):
    from src.screens.trailing import screen_balance_sheet

    df = screen_balance_sheet(loaded_db)
    row = df[df["ticker"] == "AAPL"]
    assert not row.empty
    cr = row["current_ratio"].iloc[0]
    if cr is not None and cr == cr:
        assert cr > 0


def test_balance_sheet_impossible_coverage_excludes(loaded_db):
    from src.screens.trailing import screen_balance_sheet

    # min coverage of 100000x is impossible
    df = screen_balance_sheet(loaded_db, min_interest_coverage=100_000.0)
    assert df.empty or "AAPL" not in df["ticker"].values


# ---------------------------------------------------------------------------
# Income
# ---------------------------------------------------------------------------


def test_income_returns_dataframe(loaded_db):
    from src.screens.trailing import screen_income

    df = screen_income(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "div_yield_pct" in df.columns
    assert "payout_ratio_pct" in df.columns


def test_income_aapl_yield_is_approx(loaded_db):
    from src.screens.trailing import screen_income

    df = screen_income(loaded_db)
    row = df[df["ticker"] == "AAPL"]
    assert not row.empty
    yld = row["div_yield_pct"].iloc[0]
    # fixture: forward_annual_dividend_yield = 0.0037 => 0.37%
    assert yld == pytest.approx(0.37, abs=0.1)


def test_income_yield_filter_includes(loaded_db):
    from src.screens.trailing import screen_income

    # AAPL yield ~0.37%; min 0.1% should include it
    df = screen_income(loaded_db, min_yield=0.1)
    assert "AAPL" in df["ticker"].values


def test_income_yield_filter_excludes(loaded_db):
    from src.screens.trailing import screen_income

    # AAPL yield ~0.37%; min 5% should exclude it
    df = screen_income(loaded_db, min_yield=5.0)
    assert "AAPL" not in df["ticker"].values
