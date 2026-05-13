"""Phase 6: daily forward snapshot — idempotency and coverage."""

import json
from datetime import date
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
# Analyst snapshot idempotency
# ---------------------------------------------------------------------------


def test_snapshot_same_day_does_not_duplicate(db):
    """Re-running analyst_snapshot on the same day overwrites, never duplicates."""
    from src.ingest.sections.analyst_snapshot import ingest_analyst_snapshot

    data = json.loads(FUNDAMENTALS.read_text())
    snap_date = date(2024, 1, 15)

    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=snap_date)
    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=snap_date)

    count = db.execute(
        "SELECT COUNT(*) FROM daily_forward_snapshot WHERE ticker='AAPL' AND snapshot_date=?",
        [snap_date],
    ).fetchone()[0]
    assert count == 1


def test_snapshot_different_days_creates_separate_rows(db):
    """Snapshots on different days produce separate rows."""
    from src.ingest.sections.analyst_snapshot import ingest_analyst_snapshot

    data = json.loads(FUNDAMENTALS.read_text())

    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=date(2024, 1, 15))
    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=date(2024, 1, 16))

    count = db.execute(
        "SELECT COUNT(*) FROM daily_forward_snapshot WHERE ticker='AAPL'"
    ).fetchone()[0]
    assert count == 2


def test_trend_idempotency(db):
    """analyst_estimates_history dedupes on (ticker, snapshot_date, period_end)."""
    from src.ingest.sections.analyst_snapshot import ingest_analyst_snapshot

    data = json.loads(FUNDAMENTALS.read_text())
    snap_date = date(2024, 1, 15)

    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=snap_date)
    rows_first = db.execute(
        "SELECT COUNT(*) FROM analyst_estimates_history WHERE ticker='AAPL' AND snapshot_date=?",
        [snap_date],
    ).fetchone()[0]

    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=snap_date)
    rows_second = db.execute(
        "SELECT COUNT(*) FROM analyst_estimates_history WHERE ticker='AAPL' AND snapshot_date=?",
        [snap_date],
    ).fetchone()[0]

    assert rows_first == rows_second


# ---------------------------------------------------------------------------
# Missing analyst data produces NULLs, not a failure
# ---------------------------------------------------------------------------


def test_snapshot_missing_analyst_ratings_inserts_nulls(db):
    """Missing AnalystRatings block results in a NULL-filled row, not an exception."""
    from src.ingest.sections.analyst_snapshot import ingest_analyst_snapshot

    data = {"General": {"CurrencyCode": "USD"}}
    snap_date = date(2024, 1, 15)

    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=snap_date)

    row = db.execute(
        "SELECT consensus_rating, target_price FROM daily_forward_snapshot "
        "WHERE ticker='AAPL' AND snapshot_date=?",
        [snap_date],
    ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] is None


def test_snapshot_missing_highlights_inserts_nulls(db):
    """Missing Highlights EPS estimates result in a NULL-filled row, not an exception."""
    from src.ingest.sections.analyst_snapshot import ingest_analyst_snapshot

    data = {
        "General": {"CurrencyCode": "USD"},
        "AnalystRatings": {"Rating": "2.5", "TargetPrice": "200.0"},
    }
    snap_date = date(2024, 1, 15)

    ingest_analyst_snapshot(db, "AAPL", data, snapshot_date=snap_date)

    row = db.execute(
        "SELECT consensus_rating, eps_estimate_curr_y FROM daily_forward_snapshot "
        "WHERE ticker='AAPL' AND snapshot_date=?",
        [snap_date],
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(2.5)
    assert row[1] is None


# ---------------------------------------------------------------------------
# Validation: EODHD error responses are rejected before ingest
# ---------------------------------------------------------------------------


def test_fetch_fundamentals_rejects_error_payload(monkeypatch):
    """An EODHD error-payload response raises ValueError before any data is written."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    from src.ingest import fetch

    with patch.object(fetch, "_get", return_value={"Error": "Ticker Not Found."}):
        with pytest.raises(ValueError, match="EODHD rejected ticker"):
            fetch.fetch_fundamentals("FAKE")


def test_fetch_fundamentals_rejects_missing_general_code(monkeypatch):
    """A response without General.Code raises ValueError."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    from src.ingest import fetch

    with patch.object(fetch, "_get", return_value={"General": {}}):
        with pytest.raises(ValueError, match="No valid General.Code"):
            fetch.fetch_fundamentals("FAKE")


def test_fetch_prices_rejects_error_payload(monkeypatch):
    """An EODHD prices error-payload raises ValueError."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    from src.ingest import fetch

    with patch.object(fetch, "_get", return_value={"Error": "No data found."}):
        with pytest.raises(ValueError, match="EODHD prices error"):
            fetch.fetch_prices("FAKE")


def test_add_ticker_eodhd_error_payload_leaves_universe_empty(tmp_path, db, monkeypatch):
    """When EODHD returns an error JSON (200 with Error key), add_ticker raises and no row is written."""
    monkeypatch.setenv("EODHD_API_TOKEN", "tok")

    from src.universe import add_ticker

    mock_settings = {
        "paths": {
            "raw_fundamentals": str(tmp_path / "raw/fundamentals"),
            "raw_prices": str(tmp_path / "raw/prices"),
            "archive": str(tmp_path / "archive"),
        },
        "ingest": {"archive_raw_files": False},
        "vendor": {"default_exchange": "US"},
    }

    with (
        patch(
            "src.ingest.orchestrator.fetch_fundamentals",
            side_effect=ValueError("EODHD rejected ticker: Ticker Not Found."),
        ),
        patch("src.ingest.orchestrator._settings", return_value=mock_settings),
    ):
        with pytest.raises(ValueError):
            add_ticker(db, "FAKE")

    count = db.execute("SELECT COUNT(*) FROM universe WHERE ticker='FAKE'").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# Snapshot coverage query
# ---------------------------------------------------------------------------


def test_snapshot_coverage_empty_returns_dataframe(loaded_db):
    """snapshot_coverage returns a DataFrame even with no snapshot data."""
    from src.app.queries import snapshot_coverage

    df = snapshot_coverage(loaded_db)
    import pandas as pd

    assert isinstance(df, pd.DataFrame)
    assert "ticker" in df.columns
    assert "n_days" in df.columns


def test_snapshot_coverage_counts_days(loaded_db):
    """snapshot_coverage accurately counts distinct snapshot days per ticker."""
    from src.app.queries import snapshot_coverage
    from src.ingest.sections.analyst_snapshot import ingest_analyst_snapshot

    data = json.loads(FUNDAMENTALS.read_text())
    for d in [date(2024, 1, 15), date(2024, 1, 16), date(2024, 1, 17)]:
        ingest_analyst_snapshot(loaded_db, "AAPL", data, snapshot_date=d)

    df = snapshot_coverage(loaded_db)
    row = df[df["ticker"] == "AAPL"]
    assert not row.empty
    assert int(row["n_days"].iloc[0]) >= 3
