"""Phase 5: queries layer and app imports."""

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
    return db


# ---------------------------------------------------------------------------
# Queries module imports without errors
# ---------------------------------------------------------------------------


def test_queries_import():
    from src.app import queries  # noqa: F401


def test_queries_open_warehouse_function_exists():
    from src.app.queries import open_warehouse  # noqa: F401


# ---------------------------------------------------------------------------
# universe_summary returns a DataFrame
# ---------------------------------------------------------------------------


def test_universe_summary_empty(db):
    from src.app.queries import universe_summary

    result = universe_summary(db)
    assert isinstance(result, pd.DataFrame)
    # No active tickers, so empty (or zero-row)
    assert len(result) == 0


def test_universe_summary_with_data(loaded_db):
    from src.app.queries import universe_summary

    # Insert an active universe row so the query has something to show
    loaded_db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    result = universe_summary(loaded_db)
    assert isinstance(result, pd.DataFrame)
    assert "ticker" in result.columns
    assert "price" in result.columns
    assert "pe_trailing" in result.columns
    assert "consensus_rating" in result.columns
    row = result[result["ticker"] == "AAPL"]
    assert not row.empty


# ---------------------------------------------------------------------------
# ticker_header
# ---------------------------------------------------------------------------


def test_ticker_header_missing_ticker(loaded_db):
    from src.app.queries import ticker_header

    result = ticker_header(loaded_db, "FAKE")
    assert result == {}


def test_ticker_header_aapl(loaded_db):
    from src.app.queries import ticker_header

    result = ticker_header(loaded_db, "AAPL")
    assert isinstance(result, dict)
    assert result.get("name") is not None
    assert result.get("price") is not None
    assert result.get("price") > 0


# ---------------------------------------------------------------------------
# valuation_history
# ---------------------------------------------------------------------------


def test_valuation_history_returns_dataframe(loaded_db):
    from src.app.queries import valuation_history

    df = valuation_history(loaded_db, "AAPL", years=5)
    assert isinstance(df, pd.DataFrame)
    assert "date" in df.columns
    assert "pe_trailing" in df.columns


def test_valuation_history_date_filter(loaded_db):
    from src.app.queries import valuation_history

    df1 = valuation_history(loaded_db, "AAPL", years=1)
    df5 = valuation_history(loaded_db, "AAPL", years=5)
    # 5-year window must include at least as many rows as 1-year
    assert len(df5) >= len(df1)


# ---------------------------------------------------------------------------
# quarterly_metrics
# ---------------------------------------------------------------------------


def test_quarterly_metrics(loaded_db):
    from src.app.queries import quarterly_metrics

    df = quarterly_metrics(loaded_db, "AAPL")
    assert isinstance(df, pd.DataFrame)
    assert "fiscal_period_end" in df.columns
    assert "revenue_b" in df.columns
    assert "gross_margin_pct" in df.columns


# ---------------------------------------------------------------------------
# earnings_history
# ---------------------------------------------------------------------------


def test_earnings_history(loaded_db):
    from src.app.queries import earnings_history

    df = earnings_history(loaded_db, "AAPL")
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        assert "eps_actual" in df.columns
        assert "surprise_percent" in df.columns


# ---------------------------------------------------------------------------
# analyst snapshot
# ---------------------------------------------------------------------------


def test_analyst_snapshot_returns_dict_or_none(loaded_db):
    from src.app.queries import latest_analyst_snapshot

    result = latest_analyst_snapshot(loaded_db, "AAPL")
    assert result is None or isinstance(result, dict)


def test_analyst_snapshot_missing_ticker(loaded_db):
    from src.app.queries import latest_analyst_snapshot

    result = latest_analyst_snapshot(loaded_db, "FAKE")
    assert result is None


# ---------------------------------------------------------------------------
# balance_sheet_history
# ---------------------------------------------------------------------------


def test_balance_sheet_history(loaded_db):
    from src.app.queries import balance_sheet_history

    df = balance_sheet_history(loaded_db, "AAPL")
    assert isinstance(df, pd.DataFrame)
    assert "fiscal_period_end" in df.columns
    assert "total_assets" in df.columns
    assert "net_debt" in df.columns


# ---------------------------------------------------------------------------
# universe_management_list
# ---------------------------------------------------------------------------


def test_universe_management_list_empty(db):
    from src.app.queries import universe_management_list

    df = universe_management_list(db)
    assert isinstance(df, pd.DataFrame)
    assert "ticker" in df.columns
    assert "active" in df.columns


def test_universe_management_list_with_rows(loaded_db):
    from src.app.queries import universe_management_list

    loaded_db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    df = universe_management_list(loaded_db)
    assert any(df["ticker"] == "AAPL")


# ---------------------------------------------------------------------------
# active_tickers
# ---------------------------------------------------------------------------


def test_active_tickers_empty(db):
    from src.app.queries import active_tickers

    result = active_tickers(db)
    assert result == []


def test_active_tickers_with_rows(loaded_db):
    from src.app.queries import active_tickers

    loaded_db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    result = active_tickers(loaded_db)
    assert "AAPL" in result


# ---------------------------------------------------------------------------
# warehouse_mtime returns a float
# ---------------------------------------------------------------------------


def test_warehouse_mtime_nonexistent():
    from src.app.queries import warehouse_mtime

    # Calls against a path that may or may not exist — should not raise
    result = warehouse_mtime()
    assert isinstance(result, float)
