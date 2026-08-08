"""Phase 13: Forward screens — vendor trends (13A) and snapshot history (13B)."""

from datetime import date, timedelta
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
# Schema: new columns present
# ---------------------------------------------------------------------------


def test_trend_columns_exist(db):
    cols = {row[1] for row in db.execute("PRAGMA table_info(analyst_estimates_history)").fetchall()}
    expected = {
        "eps_trend_current",
        "eps_trend_7days_ago",
        "eps_trend_30days_ago",
        "eps_trend_60days_ago",
        "eps_trend_90days_ago",
        "eps_revisions_up_last_7days",
        "eps_revisions_up_last_30days",
        "eps_revisions_down_last_7days",
        "eps_revisions_down_last_30days",
    }
    assert expected.issubset(cols)


# ---------------------------------------------------------------------------
# Parser: trend fields are ingested
# ---------------------------------------------------------------------------


def test_trend_fields_populated(loaded_db):
    result = loaded_db.execute("""
        SELECT COUNT(*) FROM analyst_estimates_history
        WHERE ticker = 'AAPL' AND eps_trend_current IS NOT NULL
    """).fetchone()[0]
    assert result > 0


def test_revision_fields_populated(loaded_db):
    result = loaded_db.execute("""
        SELECT COUNT(*) FROM analyst_estimates_history
        WHERE ticker = 'AAPL' AND eps_revisions_up_last_30days IS NOT NULL
    """).fetchone()[0]
    assert result > 0


# ---------------------------------------------------------------------------
# 13A: screen_eps_revised_up
# ---------------------------------------------------------------------------


def test_eps_revised_up_returns_dataframe(loaded_db):
    from src.screens.forward_vendor import screen_eps_revised_up

    df = screen_eps_revised_up(loaded_db)
    assert isinstance(df, pd.DataFrame)


def test_eps_revised_up_no_zero_division(loaded_db):
    from src.screens.forward_vendor import screen_eps_revised_up

    df = screen_eps_revised_up(loaded_db, lookback_days=30, min_delta_pct=0.0)
    if not df.empty:
        assert not (df["max_eps_delta_pct"].isin([float("inf"), float("-inf")])).any()


def test_eps_revised_up_min_delta_monotonic(loaded_db):
    from src.screens.forward_vendor import screen_eps_revised_up

    df_low = screen_eps_revised_up(loaded_db, min_delta_pct=0.0)
    df_high = screen_eps_revised_up(loaded_db, min_delta_pct=50.0)
    assert len(df_low) >= len(df_high)


def test_eps_revised_up_display_filter(loaded_db):
    from src.screens.forward_vendor import screen_eps_revised_up

    df_all = screen_eps_revised_up(loaded_db)
    df_filtered = screen_eps_revised_up(loaded_db, display_filter=["AAPL"])
    if not df_all.empty and "AAPL" in df_all["ticker"].values:
        assert set(df_filtered["ticker"].tolist()).issubset({"AAPL"})


# ---------------------------------------------------------------------------
# 13A: screen_net_upward_eps_revisions
# ---------------------------------------------------------------------------


def test_net_revisions_returns_dataframe(loaded_db):
    from src.screens.forward_vendor import screen_net_upward_eps_revisions

    df = screen_net_upward_eps_revisions(loaded_db)
    assert isinstance(df, pd.DataFrame)


def test_net_revisions_min_net_monotonic(loaded_db):
    from src.screens.forward_vendor import screen_net_upward_eps_revisions

    df_low = screen_net_upward_eps_revisions(loaded_db, min_net=1)
    df_high = screen_net_upward_eps_revisions(loaded_db, min_net=100)
    assert len(df_low) >= len(df_high)


# ---------------------------------------------------------------------------
# 13A: screen_beat_and_revise
# ---------------------------------------------------------------------------


def test_beat_and_revise_returns_dataframe(loaded_db):
    from src.screens.forward_vendor import screen_beat_and_revise

    df = screen_beat_and_revise(loaded_db)
    assert isinstance(df, pd.DataFrame)


def test_beat_and_revise_surprise_monotonic(loaded_db):
    from src.screens.forward_vendor import screen_beat_and_revise

    df_low = screen_beat_and_revise(loaded_db, min_surprise_pct=0.0)
    df_high = screen_beat_and_revise(loaded_db, min_surprise_pct=100.0)
    assert len(df_low) >= len(df_high)


# ---------------------------------------------------------------------------
# 13B: insufficient-history gating
# ---------------------------------------------------------------------------


def _insert_snapshots(db, ticker: str, n_days: int, base_rating: float = 4.0) -> None:
    today = date.today()
    for i in range(n_days):
        snap_date = today - timedelta(days=n_days - 1 - i)
        db.execute(
            """
            INSERT INTO daily_forward_snapshot
                (ticker, snapshot_date, consensus_rating, target_price, currency, loaded_at)
            VALUES (?, ?, ?, ?, 'USD', now())
            ON CONFLICT (ticker, snapshot_date) DO NOTHING
            """,
            [ticker, snap_date, base_rating, 200.0],
        )


def test_rating_shift_excludes_insufficient_history(db):
    from src.ingest.orchestrator import ingest_ticker
    from src.screens.forward_history import screen_consensus_rating_shift

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    # Insert only 5 days — below the 30-day threshold
    _insert_snapshots(db, "AAPL", n_days=5)
    _, n_excluded = screen_consensus_rating_shift(db, min_history_days=30)
    assert n_excluded == 1


def test_rating_shift_detects_change(db):
    from src.ingest.orchestrator import ingest_ticker
    from src.screens.forward_history import screen_consensus_rating_shift

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    # Clear any snapshots loaded by ingest so test data is authoritative
    db.execute("DELETE FROM daily_forward_snapshot WHERE ticker = 'AAPL'")
    # Insert 35 days with rating shift: start at 4.0, end at 2.5 (upgrade)
    today = date.today()
    for i in range(35):
        snap_date = today - timedelta(days=34 - i)
        rating = 4.0 if i < 20 else 2.5
        db.execute(
            """
            INSERT INTO daily_forward_snapshot
                (ticker, snapshot_date, consensus_rating, target_price, currency, loaded_at)
            VALUES (?, ?, ?, ?, 'USD', now())
            ON CONFLICT (ticker, snapshot_date) DO NOTHING
            """,
            ["AAPL", snap_date, rating, 200.0],
        )
    df, n_excluded = screen_consensus_rating_shift(
        db, lookback_days=30, min_shift=1.0, min_history_days=30
    )
    assert n_excluded == 0
    assert "AAPL" in df["ticker"].values


def test_target_price_raised_excludes_insufficient_history(db):
    from src.ingest.orchestrator import ingest_ticker
    from src.screens.forward_history import screen_target_price_raised

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    _insert_snapshots(db, "AAPL", n_days=5)
    _, n_excluded = screen_target_price_raised(db, min_history_days=30)
    assert n_excluded == 1


def test_target_price_raised_detects_change(db):
    from src.ingest.orchestrator import ingest_ticker
    from src.screens.forward_history import screen_target_price_raised

    ingest_ticker(db, FUNDAMENTALS, PRICES)
    db.execute(
        "INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)"
        " ON CONFLICT (ticker) DO UPDATE SET active = true"
    )
    # Clear snapshots loaded by ingest so test data is authoritative
    db.execute("DELETE FROM daily_forward_snapshot WHERE ticker = 'AAPL'")
    today = date.today()
    for i in range(35):
        snap_date = today - timedelta(days=34 - i)
        tp = 200.0 if i < 5 else 220.0  # +10% raise after day 5
        db.execute(
            """
            INSERT INTO daily_forward_snapshot
                (ticker, snapshot_date, consensus_rating, target_price, currency, loaded_at)
            VALUES (?, ?, ?, ?, 'USD', now())
            ON CONFLICT (ticker, snapshot_date) DO NOTHING
            """,
            ["AAPL", snap_date, 4.0, tp],
        )
    df, n_excluded = screen_target_price_raised(
        db, lookback_days=30, min_change_pct=5.0, min_history_days=30
    )
    assert n_excluded == 0
    assert "AAPL" in df["ticker"].values


# ---------------------------------------------------------------------------
# Watchlist interaction: display_filter respected in 13A
# ---------------------------------------------------------------------------


def test_13a_display_filter_applied(loaded_db):
    from src.screens.forward_vendor import screen_net_upward_eps_revisions

    df_none = screen_net_upward_eps_revisions(loaded_db, min_net=1, display_filter=["NONEXISTENT"])
    assert len(df_none) == 0 or df_none.empty
