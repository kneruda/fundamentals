"""Phase 8: sector view + bulk ticker upload."""

from pathlib import Path
from unittest.mock import patch

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
# sector_summary
# ---------------------------------------------------------------------------


def test_sector_summary_returns_dataframe(loaded_db):
    from src.screens.sectors import sector_summary

    df = sector_summary(loaded_db)
    assert isinstance(df, pd.DataFrame)
    assert "sector" in df.columns
    assert "n_tickers" in df.columns
    assert "median_pe" in df.columns


def test_sector_summary_has_one_row_for_aapl(loaded_db):
    from src.screens.sectors import sector_summary

    df = sector_summary(loaded_db)
    assert len(df) == 1
    assert df.iloc[0]["n_tickers"] == 1


def test_sector_summary_median_pe_matches_trailing(loaded_db):
    """With a single-ticker sector, median P/E equals the ticker's own trailing P/E."""
    from src.screens.sectors import sector_summary
    from src.screens.trailing import screen_absolute_valuation

    summary = sector_summary(loaded_db)
    individual = screen_absolute_valuation(loaded_db)

    sector_pe = summary["median_pe"].iloc[0]
    aapl_pe = individual.loc[individual["ticker"] == "AAPL", "pe_trailing"].iloc[0]

    assert sector_pe == pytest.approx(aapl_pe, rel=0.01)


# ---------------------------------------------------------------------------
# sector_constituents
# ---------------------------------------------------------------------------


def test_sector_constituents_returns_aapl(loaded_db):
    from src.screens.sectors import sector_constituents, sector_summary

    summary = sector_summary(loaded_db)
    sector = summary["sector"].iloc[0]

    df = sector_constituents(loaded_db, sector)
    assert "AAPL" in df["ticker"].values


def test_sector_constituents_unknown_sector_is_empty(loaded_db):
    from src.screens.sectors import sector_constituents

    df = sector_constituents(loaded_db, "NoSuchSector")
    assert df.empty


def test_sector_constituents_columns(loaded_db):
    from src.screens.sectors import sector_constituents, sector_summary

    sector = sector_summary(loaded_db)["sector"].iloc[0]
    df = sector_constituents(loaded_db, sector)
    for col in ["ticker", "name", "pe_trailing", "rev_yoy_pct"]:
        assert col in df.columns


# ---------------------------------------------------------------------------
# parse_tickers
# ---------------------------------------------------------------------------


def test_parse_tickers_strips_blank_lines():
    from src.universe import parse_tickers

    result = parse_tickers("AAPL\n\n  \nMSFT\n")
    assert result == ["AAPL", "MSFT"]


def test_parse_tickers_strips_comment_lines():
    from src.universe import parse_tickers

    result = parse_tickers("# this is a comment\nAAPL\n# another\nMSFT")
    assert result == ["AAPL", "MSFT"]


def test_parse_tickers_uppercases():
    from src.universe import parse_tickers

    result = parse_tickers("aapl\nmsft")
    assert result == ["AAPL", "MSFT"]


def test_parse_tickers_empty_input():
    from src.universe import parse_tickers

    assert parse_tickers("") == []
    assert parse_tickers("# only comments\n\n") == []


def test_parse_tickers_bare_ticker_unchanged():
    from src.universe import parse_tickers

    result = parse_tickers("SHOP")
    assert result == ["SHOP"]


# ---------------------------------------------------------------------------
# bulk_add_tickers
# ---------------------------------------------------------------------------


def test_bulk_add_all_succeed(db):
    from src.universe import bulk_add_tickers

    def fake_add(con, ticker, notes=None):
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )

    with patch("src.universe.add_ticker", side_effect=fake_add):
        results = bulk_add_tickers(db, ["AAPL", "MSFT"])

    assert len(results) == 2
    assert all(ok for _, ok, _ in results)
    assert {t for t, _, _ in results} == {"AAPL", "MSFT"}


def test_bulk_add_one_failure_rest_succeed(db):
    from src.universe import bulk_add_tickers

    def fake_add(con, ticker, notes=None):
        if ticker == "FAKE":
            raise ValueError("ticker not found")
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )

    with patch("src.universe.add_ticker", side_effect=fake_add):
        results = bulk_add_tickers(db, ["AAPL", "FAKE", "MSFT"])

    ok_map = {t: ok for t, ok, _ in results}
    assert ok_map["AAPL"] is True
    assert ok_map["FAKE"] is False
    assert ok_map["MSFT"] is True

    # No partial-ingest universe row for FAKE
    count = db.execute("SELECT COUNT(*) FROM universe WHERE ticker = 'FAKE'").fetchone()[0]
    assert count == 0


def test_bulk_add_idempotent(db):
    """Bulk-adding a ticker already present does not duplicate the universe row."""
    from src.universe import bulk_add_tickers

    db.execute("INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)")

    def fake_add(con, ticker, notes=None):
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )

    with patch("src.universe.add_ticker", side_effect=fake_add):
        results = bulk_add_tickers(db, ["AAPL"])

    assert results[0][1] is True
    assert results[0][2] == "already present, refreshed"
    count = db.execute("SELECT COUNT(*) FROM universe WHERE ticker = 'AAPL'").fetchone()[0]
    assert count == 1


def test_bulk_add_empty_list(db):
    from src.universe import bulk_add_tickers

    results = bulk_add_tickers(db, [])
    assert results == []
