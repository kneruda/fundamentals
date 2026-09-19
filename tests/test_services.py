"""Regression tests for UI-neutral service boundaries introduced in Phase 2."""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def loaded_db():
    from src.ingest.orchestrator import ingest_ticker
    from src.schema.runner import open_db

    con = open_db(":memory:")
    ingest_ticker(con, FIXTURES / "AAPL-Fundamentals.json", FIXTURES / "AAPL.json")
    con.execute("INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)")
    yield con
    con.close()


def test_streamlit_query_import_remains_a_compatibility_facade():
    from src.app import queries as streamlit_queries
    from src.services import queries

    assert streamlit_queries.universe_summary is queries.universe_summary


def test_display_filter_is_resolved_without_ui_state(loaded_db):
    from src.services.watchlists import display_filter_for_watchlist
    from src.watchlist import create_watchlist

    watchlist_id = create_watchlist(loaded_db, "Core", ["AAPL"])

    assert display_filter_for_watchlist(loaded_db, None) is None
    assert display_filter_for_watchlist(loaded_db, watchlist_id) == ["AAPL"]


def test_fundamental_screener_dispatch_preserves_existing_screen_result(loaded_db):
    from src.services.screeners import run_fundamental_screen

    result = run_fundamental_screen(
        loaded_db,
        "absolute_valuation",
        display_filter=["AAPL"],
        filters={"min_fcf_yield": 1.0},
    )

    assert result.excluded_count == 0
    assert result.rows["ticker"].tolist() == ["AAPL"]


def test_screener_dispatch_rejects_unknown_screen(loaded_db):
    from src.services.screeners import run_technical_screen

    with pytest.raises(ValueError, match="Unsupported screen"):
        run_technical_screen(loaded_db, "not-a-screen")  # type: ignore[arg-type]
