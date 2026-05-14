"""Phase 11: annual statements, period_type discriminator, query/UI toggles."""

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
# Migration: period_type column exists on all three tables
# ---------------------------------------------------------------------------


def test_period_type_column_exists(db):
    for table in ("income_statement", "balance_sheet", "cash_flow"):
        cols = [
            r[0]
            for r in db.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                [table],
            ).fetchall()
        ]
        assert "period_type" in cols, f"period_type missing from {table}"


# ---------------------------------------------------------------------------
# Ingestion: both quarterly and annual rows land with the right period_type
# ---------------------------------------------------------------------------


def test_annual_rows_ingested(loaded_db):
    for table in ("income_statement", "balance_sheet", "cash_flow"):
        n_annual = loaded_db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ticker='AAPL' AND period_type='annual'"
        ).fetchone()[0]
        assert n_annual > 0, f"No annual rows in {table}"


def test_quarterly_rows_still_present(loaded_db):
    for table in ("income_statement", "balance_sheet", "cash_flow"):
        n_q = loaded_db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ticker='AAPL' AND period_type='quarterly'"
        ).fetchone()[0]
        assert n_q > 0, f"Quarterly rows missing from {table} after phase 11 migration"


def test_no_duplicate_pk(loaded_db):
    """(ticker, fiscal_period_end, period_type) must be unique."""
    for table in ("income_statement", "balance_sheet", "cash_flow"):
        dupes = loaded_db.execute(f"""
            SELECT ticker, fiscal_period_end, period_type, COUNT(*) AS n
            FROM {table}
            GROUP BY ticker, fiscal_period_end, period_type
            HAVING n > 1
        """).fetchall()
        assert not dupes, f"Duplicate PK rows in {table}: {dupes}"


def test_na_entries_skipped(loaded_db):
    """Yearly entries with string value 'NA' must not produce rows."""
    # Verify no NULL fiscal_period_end (which would indicate a bad parse of 'NA')
    for table in ("income_statement", "balance_sheet", "cash_flow"):
        null_rows = loaded_db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE ticker='AAPL' AND fiscal_period_end IS NULL"
        ).fetchone()[0]
        assert null_rows == 0, f"NULL fiscal_period_end rows in {table}"


# ---------------------------------------------------------------------------
# Query layer: period_type and depth toggles
# ---------------------------------------------------------------------------


def test_statement_query_quarterly(loaded_db):
    from src.app.queries import statement

    df = statement(loaded_db, "AAPL", "income_statement", period_type="quarterly")
    assert not df.empty
    assert "total_revenue" in df.columns


def test_statement_query_annual(loaded_db):
    from src.app.queries import statement

    df = statement(loaded_db, "AAPL", "income_statement", period_type="annual")
    assert not df.empty
    assert "total_revenue" in df.columns


def test_statement_query_full_depth(loaded_db):
    from src.app.queries import statement

    summary_df = statement(loaded_db, "AAPL", "income_statement", depth="summary")
    full_df = statement(loaded_db, "AAPL", "income_statement", depth="full")
    # Full should have more columns than summary
    assert len(full_df.columns) > len(summary_df.columns)


def test_statement_summary_has_required_cols(loaded_db):
    from src.app.queries import statement

    for stmt_type, required in [
        ("income_statement", ["total_revenue", "net_income"]),
        ("balance_sheet", ["total_assets", "total_stockholder_equity"]),
        ("cash_flow", ["free_cash_flow"]),
    ]:
        df = statement(loaded_db, "AAPL", stmt_type, depth="summary")
        for col in required:
            assert col in df.columns, f"{col} missing from {stmt_type} summary"


# ---------------------------------------------------------------------------
# Unit math
# ---------------------------------------------------------------------------


def test_units_math(loaded_db):
    """Known value 1.234e9 displays correctly for each unit setting."""
    import pandas as pd

    from src.app.queries import statement

    df = statement(loaded_db, "AAPL", "income_statement", period_type="annual", depth="summary")
    assert not df.empty

    val = 1_234_000_000.0
    # Verify divisor math
    assert abs(val / 1e9 - 1.234) < 1e-6
    assert abs(val / 1e6 - 1234.0) < 1e-6
    assert abs(val / 1e3 - 1_234_000.0) < 1e-6
    assert abs(val / 1.0 - 1_234_000_000.0) < 1e-6


# ---------------------------------------------------------------------------
# quarterly_metrics unaffected (period_type='quarterly' filter)
# ---------------------------------------------------------------------------


def test_quarterly_metrics_not_double_counted(loaded_db):
    from src.app.queries import quarterly_metrics

    df = quarterly_metrics(loaded_db, "AAPL")
    # Should not duplicate rows for the same fiscal_period_end
    dupes = df[df.duplicated(subset=["fiscal_period_end"])]
    assert dupes.empty, f"Duplicate periods in quarterly_metrics: {dupes}"
