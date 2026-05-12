"""Phase 3: universe management (add, remove, list, seed)."""

import json
from pathlib import Path
from unittest.mock import patch

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


def _mock_settings(tmp_path):
    return {
        "paths": {
            "raw_fundamentals": str(tmp_path / "raw/fundamentals"),
            "raw_prices": str(tmp_path / "raw/prices"),
            "archive": str(tmp_path / "archive"),
        },
        "ingest": {"archive_raw_files": False},
        "vendor": {"default_exchange": "US"},
    }


# ---------------------------------------------------------------------------
# add_ticker
# ---------------------------------------------------------------------------


def test_add_ticker_invalid_leaves_universe_empty(db):
    """Invalid ticker raises and does not write a universe row."""
    from src.universe import add_ticker

    with patch("src.universe.fetch_and_ingest", side_effect=RuntimeError("not found")):
        with pytest.raises(RuntimeError):
            add_ticker(db, "FAKE")

    count = db.execute("SELECT COUNT(*) FROM universe WHERE ticker='FAKE'").fetchone()[0]
    assert count == 0


def test_add_ticker_valid_populates_warehouse(tmp_path, db, monkeypatch):
    """Valid ticker inserts a universe row and loads data into the warehouse."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")
    fund_data = json.loads(FUNDAMENTALS.read_text())
    price_data = json.loads(PRICES.read_text())

    from src.universe import add_ticker

    with (
        patch("src.ingest.fetch.fetch_fundamentals", return_value=fund_data),
        patch("src.ingest.fetch.fetch_prices", return_value=price_data),
        patch("src.ingest.orchestrator._settings", return_value=_mock_settings(tmp_path)),
    ):
        add_ticker(db, "AAPL")

    row = db.execute("SELECT ticker, active FROM universe WHERE ticker='AAPL'").fetchone()
    assert row is not None
    assert row[1] is True

    assert db.execute("SELECT COUNT(*) FROM security_master WHERE ticker='AAPL'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM prices_daily WHERE ticker='AAPL'").fetchone()[0] > 0


def test_add_ticker_idempotent(tmp_path, db, monkeypatch):
    """Calling add_ticker twice does not create duplicate universe rows."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")
    fund_data = json.loads(FUNDAMENTALS.read_text())
    price_data = json.loads(PRICES.read_text())

    from src.universe import add_ticker

    with (
        patch("src.ingest.fetch.fetch_fundamentals", return_value=fund_data),
        patch("src.ingest.fetch.fetch_prices", return_value=price_data),
        patch("src.ingest.orchestrator._settings", return_value=_mock_settings(tmp_path)),
    ):
        add_ticker(db, "AAPL")
        add_ticker(db, "AAPL")

    count = db.execute("SELECT COUNT(*) FROM universe WHERE ticker='AAPL'").fetchone()[0]
    assert count == 1


def test_add_ticker_preserves_canonical_ticker(tmp_path, db, monkeypatch):
    """Canonical ticker (e.g. 7203.TSE) is stored even when General.Code is bare."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    # Return data where General.Code is just the bare symbol (as EODHD does)
    fund_data = json.loads(FUNDAMENTALS.read_text())
    fund_data["General"]["Code"] = "7203"
    fund_data["General"]["Exchange"] = "TSE"
    price_data = json.loads(PRICES.read_text())

    from src.universe import add_ticker

    with (
        patch("src.ingest.fetch.fetch_fundamentals", return_value=fund_data),
        patch("src.ingest.fetch.fetch_prices", return_value=price_data),
        patch("src.ingest.orchestrator._settings", return_value=_mock_settings(tmp_path)),
    ):
        add_ticker(db, "7203.TSE")

    # universe row should use the canonical "7203.TSE", not the bare "7203"
    row = db.execute("SELECT ticker FROM universe WHERE ticker='7203.TSE'").fetchone()
    assert row is not None

    # warehouse data should also be keyed on "7203.TSE"
    assert (
        db.execute("SELECT COUNT(*) FROM security_master WHERE ticker='7203.TSE'").fetchone()[0]
        == 1
    )


# ---------------------------------------------------------------------------
# remove_ticker
# ---------------------------------------------------------------------------


def test_remove_ticker_soft_deletes(db):
    """remove_ticker sets active=false and preserves the row."""
    db.execute("INSERT INTO universe (ticker, active) VALUES ('AAPL', true)")

    from src.universe import remove_ticker

    remove_ticker(db, "AAPL")

    row = db.execute("SELECT active FROM universe WHERE ticker='AAPL'").fetchone()
    assert row is not None
    assert row[0] is False


def test_remove_add_roundtrip(tmp_path, db, monkeypatch):
    """remove then add re-activates the ticker with no duplicate rows."""
    db.execute("INSERT INTO universe (ticker, active) VALUES ('AAPL', true)")

    from src.universe import add_ticker, remove_ticker

    remove_ticker(db, "AAPL")
    assert db.execute("SELECT active FROM universe WHERE ticker='AAPL'").fetchone()[0] is False

    monkeypatch.setenv("EODHD_API_TOKEN", "tok")
    fund_data = json.loads(FUNDAMENTALS.read_text())
    price_data = json.loads(PRICES.read_text())

    with (
        patch("src.ingest.fetch.fetch_fundamentals", return_value=fund_data),
        patch("src.ingest.fetch.fetch_prices", return_value=price_data),
        patch("src.ingest.orchestrator._settings", return_value=_mock_settings(tmp_path)),
    ):
        add_ticker(db, "AAPL")

    row = db.execute("SELECT ticker, active FROM universe WHERE ticker='AAPL'").fetchone()
    assert row[1] is True
    assert db.execute("SELECT COUNT(*) FROM universe WHERE ticker='AAPL'").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# list_universe
# ---------------------------------------------------------------------------


def test_list_universe_active_only(db):
    db.execute("INSERT INTO universe (ticker, active) VALUES ('AAPL', true)")
    db.execute("INSERT INTO universe (ticker, active) VALUES ('MSFT', false)")

    from src.universe import list_universe

    result = list_universe(db, active_only=True)
    assert len(result) == 1
    assert result.iloc[0]["ticker"] == "AAPL"


def test_list_universe_all(db):
    db.execute("INSERT INTO universe (ticker, active) VALUES ('AAPL', true)")
    db.execute("INSERT INTO universe (ticker, active) VALUES ('MSFT', false)")

    from src.universe import list_universe

    result = list_universe(db, active_only=False)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# seed_from_config
# ---------------------------------------------------------------------------


def test_seed_skips_existing(tmp_path, db):
    """seed_from_config skips tickers already in the universe table."""
    db.execute("INSERT INTO universe (ticker, active) VALUES ('AAPL', true)")

    yaml_path = tmp_path / "universe.yml"
    yaml_path.write_text("tickers:\n  - AAPL\n  - MSFT\n")

    called = []

    def fake_fetch_and_ingest(con, ticker):
        called.append(ticker)

    from src.universe import seed_from_config

    with patch("src.universe.fetch_and_ingest", side_effect=fake_fetch_and_ingest):
        seed_from_config(db, yaml_path)

    assert "AAPL" not in called
    assert "MSFT" in called
    assert db.execute("SELECT COUNT(*) FROM universe WHERE ticker='MSFT'").fetchone()[0] == 1


def test_seed_idempotent(tmp_path, db):
    """Running seed_from_config twice does not duplicate universe rows."""
    yaml_path = tmp_path / "universe.yml"
    yaml_path.write_text("tickers:\n  - AAPL\n")

    from src.universe import seed_from_config

    with patch("src.universe.fetch_and_ingest"):
        seed_from_config(db, yaml_path)
        seed_from_config(db, yaml_path)

    count = db.execute("SELECT COUNT(*) FROM universe WHERE ticker='AAPL'").fetchone()[0]
    assert count == 1


def test_seed_one_failure_does_not_abort(tmp_path, db):
    """A failure seeding one ticker does not prevent the rest from being seeded."""
    yaml_path = tmp_path / "universe.yml"
    yaml_path.write_text("tickers:\n  - BAD\n  - AAPL\n")

    def fake_fai(con, ticker):
        if ticker == "BAD":
            raise RuntimeError("bad ticker")

    from src.universe import seed_from_config

    with patch("src.universe.fetch_and_ingest", side_effect=fake_fai):
        seed_from_config(db, yaml_path)

    assert db.execute("SELECT COUNT(*) FROM universe WHERE ticker='AAPL'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM universe WHERE ticker='BAD'").fetchone()[0] == 0
