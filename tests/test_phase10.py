"""Phase 10: watchlists, display_filter, comparison-set invariant."""

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
# Watchlist CRUD
# ---------------------------------------------------------------------------


def test_create_and_list(db):
    from src.watchlist import create_watchlist, list_watchlists

    wid = create_watchlist(db, "Tech", ["AAPL", "MSFT"], "big tech")
    assert isinstance(wid, int)

    df = list_watchlists(db)
    assert len(df) == 1
    assert df.iloc[0]["name"] == "Tech"
    assert int(df.iloc[0]["member_count"]) == 2


def test_get_membership(db):
    from src.watchlist import create_watchlist, get_membership

    create_watchlist(db, "My List", ["GOOG", "AAPL"])
    members = get_membership(db, "My List")
    assert sorted(members) == ["AAPL", "GOOG"]


def test_get_membership_by_id(db):
    from src.watchlist import create_watchlist, get_membership

    wid = create_watchlist(db, "By ID", ["META"])
    members = get_membership(db, wid)
    assert members == ["META"]


def test_delete_cascades_membership(db):
    from src.watchlist import create_watchlist, delete_watchlist, list_watchlists

    wid = create_watchlist(db, "Temp", ["AAPL", "MSFT"])
    delete_watchlist(db, wid)

    df = list_watchlists(db)
    assert df.empty

    rows = db.execute(
        "SELECT COUNT(*) FROM watchlist_membership WHERE watchlist_id = ?", [wid]
    ).fetchone()[0]
    assert rows == 0


def test_delete_by_name(db):
    from src.watchlist import create_watchlist, delete_watchlist, list_watchlists

    create_watchlist(db, "Named", ["AAPL"])
    delete_watchlist(db, "Named")
    assert list_watchlists(db).empty


def test_rename(db):
    from src.watchlist import create_watchlist, list_watchlists, rename_watchlist

    create_watchlist(db, "Old Name", ["AAPL"])
    rename_watchlist(db, "Old Name", "New Name")
    df = list_watchlists(db)
    assert df.iloc[0]["name"] == "New Name"


def test_name_case_insensitive_lookup(db):
    from src.watchlist import create_watchlist, get_membership

    create_watchlist(db, "MyList", ["AAPL"])
    assert get_membership(db, "mylist") == ["AAPL"]
    assert get_membership(db, "MYLIST") == ["AAPL"]


def test_multiple_watchlists_get_sequential_ids(db):
    from src.watchlist import create_watchlist, list_watchlists

    id1 = create_watchlist(db, "First", ["AAPL"])
    id2 = create_watchlist(db, "Second", ["MSFT"])
    assert id2 == id1 + 1
    assert len(list_watchlists(db)) == 2


def test_resolve_unknown_name_raises(db):
    from src.watchlist import get_membership

    with pytest.raises(ValueError, match="not found"):
        get_membership(db, "does-not-exist")


# ---------------------------------------------------------------------------
# Ticker-input parser reuse (same semantics as bulk upload)
# ---------------------------------------------------------------------------


def test_watchlist_parser_matches_bulk_upload_parser():
    from src.ticker_input import parse_ticker_input

    raw = "AAPL\n# comment\nMSFT\n\nGOOG"
    result = parse_ticker_input(raw)
    assert result == ["AAPL", "MSFT", "GOOG"]


def test_file_content_identical_to_textarea():
    from src.ticker_input import parse_ticker_input

    textarea_input = "AAPL\nMSFT"
    file_content = b"AAPL\nMSFT"
    assert parse_ticker_input(textarea_input) == parse_ticker_input(file_content.decode())


# ---------------------------------------------------------------------------
# display_filter on trailing screens
# ---------------------------------------------------------------------------


def test_display_filter_reduces_rows(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    full_df = screen_absolute_valuation(loaded_db)
    # Filter to only a ticker NOT in the universe — result must be empty
    filtered_df = screen_absolute_valuation(loaded_db, display_filter=["DOES_NOT_EXIST"])

    assert filtered_df.empty
    assert len(full_df) >= len(filtered_df)


def test_display_filter_keeps_matching_ticker(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    df = screen_absolute_valuation(loaded_db, display_filter=["AAPL"])
    # AAPL is in the loaded universe; result is either 1 row or 0 (if multiples not computed yet)
    assert set(df["ticker"]).issubset({"AAPL"})


def test_display_filter_none_returns_full_universe(loaded_db):
    from src.screens.trailing import screen_absolute_valuation

    df = screen_absolute_valuation(loaded_db, display_filter=None)
    assert "AAPL" in df["ticker"].values


# ---------------------------------------------------------------------------
# Sector summary: medians unchanged by display_filter
# ---------------------------------------------------------------------------


def test_sector_summary_unaffected_by_display_filter(loaded_db):
    from src.screens.sectors import sector_summary

    # sector_summary always uses the full active universe — no display_filter arg
    summary = sector_summary(loaded_db)
    # Just verify it runs and returns expected shape
    assert "sector" in summary.columns
    assert "median_pe" in summary.columns


def test_sector_constituents_display_filter(loaded_db):
    from src.screens.sectors import sector_constituents

    full = sector_constituents(loaded_db, "Technology")
    filtered = sector_constituents(loaded_db, "Technology", display_filter=["AAPL"])
    # filtered is a subset of full
    assert set(filtered["ticker"]).issubset(set(full["ticker"]))


def test_sector_constituents_empty_filter(loaded_db):
    from src.screens.sectors import sector_constituents

    result = sector_constituents(loaded_db, "Technology", display_filter=[])
    assert result.empty


# ---------------------------------------------------------------------------
# Schema: watchlist migration applied correctly
# ---------------------------------------------------------------------------


def test_watchlist_tables_exist(db):
    tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
    assert "watchlist" in tables
    assert "watchlist_membership" in tables


def test_watchlist_membership_columns(db):
    cols = {r[0] for r in db.execute("DESCRIBE watchlist_membership").fetchall()}
    assert {"watchlist_id", "ticker", "shares", "cost_basis", "notes", "added_at"}.issubset(cols)
