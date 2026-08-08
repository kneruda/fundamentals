"""Phase 9: ticker-input parser, bulk loader, load monitoring."""

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
# parse_ticker_input
# ---------------------------------------------------------------------------


def test_parse_ticker_input_handles_textarea():
    from src.ticker_input import parse_ticker_input

    result = parse_ticker_input("AAPL\n\nMSFT\n# comment\n  GOOG  ")
    assert result == ["AAPL", "MSFT", "GOOG"]


def test_parse_ticker_input_handles_blank_and_comments():
    from src.ticker_input import parse_ticker_input

    result = parse_ticker_input("# header\n\nAAPL\n# another comment\n\n")
    assert result == ["AAPL"]


def test_parse_ticker_input_empty():
    from src.ticker_input import parse_ticker_input

    assert parse_ticker_input("") == []
    assert parse_ticker_input("# only comments\n\n") == []


def test_parse_ticker_input_uppercases():
    from src.ticker_input import parse_ticker_input

    assert parse_ticker_input("aapl\nmsft") == ["AAPL", "MSFT"]


def test_parse_ticker_input_same_as_parse_tickers():
    """parse_ticker_input and universe.parse_tickers produce identical results."""
    from src.ticker_input import parse_ticker_input
    from src.universe import parse_tickers

    sample = "# comment\nAAPL\n\n  MSFT  \nSHOP.TO\n"
    assert parse_ticker_input(sample) == parse_tickers(sample)


# ---------------------------------------------------------------------------
# load_runs populated by fetch_and_ingest
# ---------------------------------------------------------------------------


def test_load_runs_recorded_on_success(db, tmp_path):
    """A successful fetch_and_ingest writes an ok row to load_runs."""
    from src.ingest.orchestrator import fetch_and_ingest

    raw_dir = tmp_path / "fundamentals"
    price_dir = tmp_path / "prices"
    raw_dir.mkdir()
    price_dir.mkdir()

    # Write fixture files today so _fresh_today skips the network fetch
    (raw_dir / "AAPL.json").write_text(FUNDAMENTALS.read_text())
    (price_dir / "AAPL.json").write_text(PRICES.read_text())

    with patch("src.ingest.orchestrator._settings") as mock_cfg:
        mock_cfg.return_value = {
            "paths": {
                "raw_fundamentals": str(raw_dir),
                "raw_prices": str(price_dir),
                "archive": str(tmp_path / "archive"),
            },
            "ingest": {"archive_raw_files": False},
        }
        fetch_and_ingest(db, "AAPL")

    count = db.execute(
        "SELECT COUNT(*) FROM load_runs WHERE ticker = 'AAPL' AND status = 'ok'"
    ).fetchone()[0]
    assert count == 1


def test_load_runs_recorded_on_failure(db, tmp_path):
    """A failed fetch_and_ingest writes a failed row to load_runs."""
    from src.ingest.orchestrator import fetch_and_ingest

    with (
        patch("src.ingest.orchestrator.fetch_fundamentals", side_effect=ValueError("bad ticker")),
        patch("src.ingest.orchestrator._settings") as mock_cfg,
    ):
        mock_cfg.return_value = {
            "paths": {
                "raw_fundamentals": str(tmp_path / "fundamentals"),
                "raw_prices": str(tmp_path / "prices"),
                "archive": str(tmp_path / "archive"),
            },
            "ingest": {"archive_raw_files": False},
        }
        with pytest.raises(ValueError):
            fetch_and_ingest(db, "FAKE")

    row = db.execute("SELECT status, error_message FROM load_runs WHERE ticker = 'FAKE'").fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert "bad ticker" in row[1]


# ---------------------------------------------------------------------------
# bulk loader: create_job / run_job / checkpoint resume
# ---------------------------------------------------------------------------


def test_create_job_inserts_pending_rows(db):
    from src.ingest.bulk import create_job

    job_id = create_job(db, ["AAPL", "MSFT", "GOOG"])
    rows = db.execute(
        "SELECT ticker, status FROM bulk_load_jobs WHERE job_id = ? ORDER BY ticker",
        [job_id],
    ).fetchall()
    assert len(rows) == 3
    assert all(status == "pending" for _, status in rows)
    tickers = [t for t, _ in rows]
    assert tickers == ["AAPL", "GOOG", "MSFT"]


def test_run_job_all_succeed(db):
    from src.ingest.bulk import create_job, run_job

    def fake_add(con, ticker, notes=None):
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )
        con.execute(
            "INSERT INTO load_runs (ticker, status, duration_ms) VALUES (?, 'ok', 100)",
            [ticker],
        )

    job_id = create_job(db, ["AAPL", "MSFT"])
    with (
        patch("src.ingest.bulk.add_ticker", side_effect=fake_add),
        patch("src.ingest.bulk._bulk_rpm", return_value=600.0),  # 0.1s sleep to keep test fast
    ):
        results = run_job(db, job_id)

    assert len(results) == 2
    assert all(ok for _, ok, _ in results)

    statuses = db.execute(
        "SELECT status FROM bulk_load_jobs WHERE job_id = ? ORDER BY ticker", [job_id]
    ).fetchall()
    assert all(s[0] == "ok" for s in statuses)


def test_run_job_one_failure_rest_succeed(db):
    from src.ingest.bulk import create_job, run_job

    def fake_add(con, ticker, notes=None):
        if ticker == "FAKE":
            raise ValueError("ticker not found")
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )

    job_id = create_job(db, ["AAPL", "FAKE", "MSFT"])
    with (
        patch("src.ingest.bulk.add_ticker", side_effect=fake_add),
        patch("src.ingest.bulk._bulk_rpm", return_value=600.0),
    ):
        results = run_job(db, job_id)

    ok_map = {t: ok for t, ok, _ in results}
    assert ok_map["AAPL"] is True
    assert ok_map["FAKE"] is False
    assert ok_map["MSFT"] is True


def test_run_job_resume_skips_completed(db):
    """Resume only processes tickers still in 'pending' state."""
    from src.ingest.bulk import create_job, run_job

    job_id = create_job(db, ["AAPL", "MSFT", "GOOG"])
    # Simulate AAPL already completed
    db.execute(
        "UPDATE bulk_load_jobs SET status = 'ok' WHERE job_id = ? AND ticker = 'AAPL'",
        [job_id],
    )

    processed = []

    def fake_add(con, ticker, notes=None):
        processed.append(ticker)
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )

    with (
        patch("src.ingest.bulk.add_ticker", side_effect=fake_add),
        patch("src.ingest.bulk._bulk_rpm", return_value=600.0),
    ):
        results = run_job(db, job_id)

    assert "AAPL" not in processed
    assert set(processed) == {"GOOG", "MSFT"}
    assert len(results) == 2


def test_run_job_no_pending_returns_empty(db):
    from src.ingest.bulk import create_job, run_job

    job_id = create_job(db, ["AAPL"])
    db.execute("UPDATE bulk_load_jobs SET status = 'ok' WHERE job_id = ?", [job_id])

    results = run_job(db, job_id)
    assert results == []


def test_run_job_unknown_job_id_raises(db):
    from src.ingest.bulk import run_job

    with pytest.raises(ValueError, match="Job not found"):
        run_job(db, "nonexistent-job-id")


def test_run_job_rate_limit_sleep(db):
    """Bulk loader sleeps between tickers according to configured RPM."""
    from src.ingest.bulk import create_job, run_job

    sleep_calls = []

    def fake_add(con, ticker, notes=None):
        con.execute(
            "INSERT INTO universe (ticker, added_at, active) VALUES (?, now(), true)"
            " ON CONFLICT (ticker) DO UPDATE SET active = true",
            [ticker],
        )

    def fake_sleep(secs):
        sleep_calls.append(secs)

    job_id = create_job(db, ["AAPL", "MSFT", "GOOG"])
    with (
        patch("src.ingest.bulk.add_ticker", side_effect=fake_add),
        patch("src.ingest.bulk.time.sleep", side_effect=fake_sleep),
        patch("src.ingest.bulk._bulk_rpm", return_value=30.0),  # 2s per ticker
    ):
        run_job(db, job_id)

    # 3 tickers → 2 sleeps (no sleep after the last one)
    assert len(sleep_calls) == 2
    assert all(abs(s - 2.0) < 0.01 for s in sleep_calls)


# ---------------------------------------------------------------------------
# universe_management_list shows monitoring columns
# ---------------------------------------------------------------------------


def test_universe_management_list_columns(loaded_db):
    from src.app.queries import universe_management_list

    df = universe_management_list(loaded_db)
    for col in ["ticker", "load_status", "price_start", "price_end", "last_load_at"]:
        assert col in df.columns


def test_universe_management_list_never_loaded(db):
    """A ticker with no load_runs entry shows 'never' status."""
    db.execute("INSERT INTO universe (ticker, added_at, active) VALUES ('TSLA', now(), true)")
    from src.app.queries import universe_management_list

    df = universe_management_list(db)
    row = df[df["ticker"] == "TSLA"].iloc[0]
    assert row["load_status"] == "never"
    import pandas as pd

    assert row["price_start"] is None or pd.isna(row["price_start"])


def test_universe_management_list_ok_status(loaded_db):
    """A ticker with a recent ok load_runs entry shows 'ok' status."""
    loaded_db.execute(
        "INSERT INTO load_runs (ticker, status, duration_ms) VALUES ('AAPL', 'ok', 500)"
    )
    from src.app.queries import universe_management_list

    df = universe_management_list(loaded_db)
    row = df[df["ticker"] == "AAPL"].iloc[0]
    assert row["load_status"] == "ok"


def test_universe_management_list_failed_status(db):
    """A ticker with a failed load_runs entry shows 'failed: ...' status."""
    db.execute("INSERT INTO universe (ticker, added_at, active) VALUES ('FAIL', now(), true)")
    db.execute(
        "INSERT INTO load_runs (ticker, status, duration_ms, error_message) "
        "VALUES ('FAIL', 'failed', 100, 'ticker not found')"
    )
    from src.app.queries import universe_management_list

    df = universe_management_list(db)
    row = df[df["ticker"] == "FAIL"].iloc[0]
    assert row["load_status"].startswith("failed:")
    assert "ticker not found" in row["load_status"]


def test_universe_management_list_price_range(loaded_db):
    """Price start/end are populated after ingest."""
    loaded_db.execute(
        "INSERT INTO load_runs (ticker, status, duration_ms) VALUES ('AAPL', 'ok', 200)"
    )
    from src.app.queries import universe_management_list

    df = universe_management_list(loaded_db)
    row = df[df["ticker"] == "AAPL"].iloc[0]
    assert row["price_start"] is not None
    assert row["price_end"] is not None
    assert str(row["price_start"]) <= str(row["price_end"])
