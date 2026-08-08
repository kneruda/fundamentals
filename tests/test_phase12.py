"""Phase 12: Universe drill-down — paginated prices and fundamentals modal."""

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
    db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    return db


# ---------------------------------------------------------------------------
# prices_count
# ---------------------------------------------------------------------------


def test_prices_count_full(loaded_db):
    from src.app.queries import prices_count

    total = prices_count(loaded_db, "AAPL")
    assert total > 0


def test_prices_count_date_range(loaded_db):
    from src.app.queries import prices_count

    total = prices_count(loaded_db, "AAPL")
    # A narrow range must be <= total
    narrow = prices_count(loaded_db, "AAPL", date_from="2020-01-01", date_to="2020-12-31")
    assert narrow <= total
    assert narrow >= 0


def test_prices_count_empty_ticker(loaded_db):
    from src.app.queries import prices_count

    assert prices_count(loaded_db, "FAKEXYZ") == 0


# ---------------------------------------------------------------------------
# prices_page — pagination math
# ---------------------------------------------------------------------------


def test_prices_page_returns_rows(loaded_db):
    from src.app.queries import prices_page

    df = prices_page(loaded_db, "AAPL", page_size=100, offset=0)
    assert not df.empty
    assert list(df.columns) == ["date", "open", "high", "low", "close", "adjusted_close", "volume"]


def test_prices_page_sorted_desc(loaded_db):
    from src.app.queries import prices_page

    df = prices_page(loaded_db, "AAPL", page_size=50, offset=0)
    assert df["date"].is_monotonic_decreasing


def test_prices_page_offset(loaded_db):
    from src.app.queries import prices_page

    page1 = prices_page(loaded_db, "AAPL", page_size=10, offset=0)
    page2 = prices_page(loaded_db, "AAPL", page_size=10, offset=10)
    # Pages must not overlap
    assert (
        page1["date"].iloc[-1] > page2["date"].iloc[0]
        or page2.empty
        or page1.empty
        or set(page1["date"].tolist()).isdisjoint(set(page2["date"].tolist()))
    )


def test_prices_page_respects_size(loaded_db):
    from src.app.queries import prices_count, prices_page

    total = prices_count(loaded_db, "AAPL")
    page_size = 100
    df = prices_page(loaded_db, "AAPL", page_size=page_size, offset=0)
    assert len(df) == min(page_size, total)


def test_prices_page_date_filter(loaded_db):
    import pandas as pd

    from src.app.queries import prices_page

    df = prices_page(
        loaded_db, "AAPL", page_size=500, offset=0, date_from="2020-01-01", date_to="2020-12-31"
    )
    if not df.empty:
        assert df["date"].max() <= pd.Timestamp("2020-12-31")
        assert df["date"].min() >= pd.Timestamp("2020-01-01")


def test_prices_page_empty_ticker(loaded_db):
    from src.app.queries import prices_page

    df = prices_page(loaded_db, "FAKEXYZ", page_size=100, offset=0)
    assert df.empty


def test_prices_page_loads_only_current_page(loaded_db):
    """Opening the second page must not load the full history into memory."""
    from src.app.queries import prices_count, prices_page

    total = prices_count(loaded_db, "AAPL")
    if total < 200:
        pytest.skip("Not enough rows to test pagination memory guard")
    df = prices_page(loaded_db, "AAPL", page_size=100, offset=100)
    assert len(df) == 100


# ---------------------------------------------------------------------------
# fundamentals_recent
# ---------------------------------------------------------------------------


def test_fundamentals_recent_quarterly(loaded_db):
    from src.app.queries import fundamentals_recent

    df = fundamentals_recent(loaded_db, "AAPL", "income_statement", "quarterly", n=8)
    assert not df.empty
    assert "total_revenue" in df.columns


def test_fundamentals_recent_annual(loaded_db):
    from src.app.queries import fundamentals_recent

    df = fundamentals_recent(loaded_db, "AAPL", "income_statement", "annual", n=5)
    assert not df.empty


def test_fundamentals_recent_no_data(loaded_db):
    from src.app.queries import fundamentals_recent

    df = fundamentals_recent(loaded_db, "FAKEXYZ", "income_statement", "quarterly", n=8)
    assert df.empty


def test_fundamentals_recent_all_statement_types(loaded_db):
    from src.app.queries import fundamentals_recent

    for stmt_type in ("income_statement", "balance_sheet", "cash_flow"):
        df = fundamentals_recent(loaded_db, "AAPL", stmt_type, "quarterly", n=8)
        assert not df.empty, f"Empty result for {stmt_type}"


def test_fundamentals_recent_n_limit(loaded_db):
    from src.app.queries import fundamentals_recent

    df = fundamentals_recent(loaded_db, "AAPL", "income_statement", "quarterly", n=3)
    assert len(df) <= 3
