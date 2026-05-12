"""Phase 1: schema + section parser tests."""

import json
from datetime import date
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
FUNDAMENTALS = FIXTURES / "AAPL-Fundamentals.json"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    from src.schema.runner import open_db

    con = open_db(":memory:")
    yield con
    con.close()


@pytest.fixture()
def loaded_db(db):
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS)
    return db


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


def test_migration_applied(db):
    applied = {r[0] for r in db.execute("SELECT version FROM _schema_migrations").fetchall()}
    assert "001_initial" in applied


def test_all_tables_exist(db):
    tables = {r[0] for r in db.execute("SHOW TABLES").fetchall()}
    expected = {
        "universe",
        "security_master",
        "quarterly_fundamentals",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "earnings_events",
        "shares_outstanding",
        "dividends_declared",
        "dividends_annual",
        "splits",
        "daily_forward_snapshot",
        "analyst_estimates_history",
        "prices_daily",
        "fx_rates_daily",
    }
    assert expected.issubset(tables)


def test_migration_idempotent(db):
    """Re-running migration runner on an already-migrated DB changes nothing."""
    from src.schema.runner import _run_migrations

    count_before = db.execute("SELECT COUNT(*) FROM _schema_migrations").fetchone()[0]
    _run_migrations(db)
    count_after = db.execute("SELECT COUNT(*) FROM _schema_migrations").fetchone()[0]
    assert count_after == count_before


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def test_to_float_conversions():
    from src.ingest.sections._util import to_float

    assert to_float(None) is None
    assert to_float("0.0944") == pytest.approx(0.0944)
    assert to_float("9.6070") == pytest.approx(9.607)
    assert to_float(0) == 0.0
    assert to_float("") is None
    assert to_float("abc") is None


def test_to_date_conversions():
    from src.ingest.sections._util import to_date

    assert to_date("2026-03-31") == date(2026, 3, 31)
    assert to_date(None) is None
    assert to_date("0000-00-00") is None
    # Fiscal-quarter label like "2026-Q1" is not a valid date; dateFormatted is used instead
    assert to_date("2026-Q1") is None


def test_col_camel_to_snake():
    from src.ingest.sections._util import col

    # Vendor typo corrections
    assert col("capitalSurpluse") == "capital_surplus"
    assert col("nonCurrrentAssetsOther") == "non_current_assets_other"
    assert col("goodWill") == "goodwill"

    # Standard conversions
    assert col("totalAssets") == "total_assets"
    assert col("commonStockSharesOutstanding") == "common_stock_shares_outstanding"
    assert col("DilutedEpsTTM") == "diluted_eps_ttm"
    assert col("freeCashFlow") == "free_cash_flow"
    assert col("changeToNetincome") == "change_to_netincome"
    assert col("totalCashflowsFromInvestingActivities") == (
        "total_cashflows_from_investing_activities"
    )


# ---------------------------------------------------------------------------
# End-to-end: all target tables populated
# ---------------------------------------------------------------------------


def test_all_target_tables_populated(loaded_db):
    tables = [
        "security_master",
        "quarterly_fundamentals",
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "earnings_events",
        "shares_outstanding",
        "dividends_declared",
        "dividends_annual",
        "splits",
        "daily_forward_snapshot",
        "analyst_estimates_history",
    ]
    for table in tables:
        count = loaded_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count > 0, f"{table} is empty after AAPL ingest"


# ---------------------------------------------------------------------------
# Section: general / security_master
# ---------------------------------------------------------------------------


def test_security_master_fields(loaded_db):
    row = loaded_db.execute(
        "SELECT code, exchange, currency_code, sector, is_delisted, fiscal_year_end"
        " FROM security_master WHERE ticker='AAPL'"
    ).fetchone()
    assert row == ("AAPL", "NASDAQ", "USD", "Technology", False, "September")


def test_security_master_ipo_date(loaded_db):
    ipo = loaded_db.execute("SELECT ipo_date FROM security_master WHERE ticker='AAPL'").fetchone()[
        0
    ]
    assert ipo == date(1980, 12, 12)


# ---------------------------------------------------------------------------
# Section: highlights / quarterly_fundamentals
# ---------------------------------------------------------------------------


def test_quarterly_fundamentals_values(loaded_db):
    row = loaded_db.execute(
        "SELECT mrq_period_end, currency, diluted_eps_ttm FROM quarterly_fundamentals"
        " WHERE ticker='AAPL'"
    ).fetchone()
    assert row[0] == date(2026, 3, 31)
    assert row[1] == "USD"
    assert row[2] == pytest.approx(8.27, rel=1e-3)


# ---------------------------------------------------------------------------
# Section: financials — balance sheet
# ---------------------------------------------------------------------------


def test_balance_sheet_row_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM balance_sheet WHERE ticker='AAPL'").fetchone()[
        0
    ]
    assert count == 163


def test_balance_sheet_report_date(loaded_db):
    """filing_date maps to report_date (point-in-time key)."""
    row = loaded_db.execute(
        "SELECT fiscal_period_end, report_date FROM balance_sheet"
        " WHERE ticker='AAPL' ORDER BY fiscal_period_end DESC LIMIT 1"
    ).fetchone()
    assert row[0] == date(2026, 3, 31)
    assert row[1] == date(2026, 5, 1)  # filing_date from JSON


def test_balance_sheet_null_fields(loaded_db):
    """BS fields absent for Apple (no goodwill, no earning assets) store as NULL."""
    row = loaded_db.execute(
        "SELECT earning_assets, goodwill FROM balance_sheet"
        " WHERE ticker='AAPL' ORDER BY fiscal_period_end DESC LIMIT 1"
    ).fetchone()
    assert row[0] is None  # earningAssets — bank-specific, always NULL for AAPL
    assert row[1] is None  # goodWill — NULL in most recent AAPL quarter


def test_balance_sheet_vendor_typo_fields(loaded_db):
    """Vendor-typo fields map to correct snake_case columns without error."""
    # non_current_assets_other from nonCurrrentAssetsOther (triple-r typo)
    val = loaded_db.execute(
        "SELECT non_current_assets_other FROM balance_sheet"
        " WHERE ticker='AAPL' ORDER BY fiscal_period_end DESC LIMIT 1"
    ).fetchone()[0]
    assert val is not None and val > 0

    # capital_surplus from capitalSurpluse (trailing-e typo) — NULL in recent AAPL period
    # (just verify the column exists and doesn't error)
    loaded_db.execute("SELECT capital_surplus FROM balance_sheet LIMIT 1").fetchone()


# ---------------------------------------------------------------------------
# Section: financials — income statement + cash flow
# ---------------------------------------------------------------------------


def test_income_statement_row_count(loaded_db):
    count = loaded_db.execute(
        "SELECT COUNT(*) FROM income_statement WHERE ticker='AAPL'"
    ).fetchone()[0]
    assert count == 163


def test_income_statement_null_optional_fields(loaded_db):
    """IS fields absent for a standard non-financial company store as NULL."""
    row = loaded_db.execute(
        "SELECT effect_of_accounting_charges, minority_interest"
        " FROM income_statement WHERE ticker='AAPL' ORDER BY fiscal_period_end DESC LIMIT 1"
    ).fetchone()
    assert row[0] is None
    assert row[1] is None


def test_cash_flow_row_count(loaded_db):
    count = loaded_db.execute("SELECT COUNT(*) FROM cash_flow WHERE ticker='AAPL'").fetchone()[0]
    assert count == 146  # CF history is shorter than BS/IS for AAPL


# ---------------------------------------------------------------------------
# Section: earnings
# ---------------------------------------------------------------------------


def test_earnings_events_row_count(loaded_db):
    count = loaded_db.execute(
        "SELECT COUNT(*) FROM earnings_events WHERE ticker='AAPL'"
    ).fetchone()[0]
    assert count == 130


def test_earnings_most_recent(loaded_db):
    row = loaded_db.execute(
        "SELECT fiscal_period_end, report_date, eps_actual, eps_estimate, surprise_percent"
        " FROM earnings_events WHERE ticker='AAPL' ORDER BY fiscal_period_end DESC LIMIT 1"
    ).fetchone()
    assert row[0] == date(2026, 3, 31)
    assert row[1] == date(2026, 4, 30)
    assert row[2] == pytest.approx(2.01)
    assert row[3] == pytest.approx(1.94)
    assert row[4] == pytest.approx(3.6082, rel=1e-3)


# ---------------------------------------------------------------------------
# Section: shares outstanding
# ---------------------------------------------------------------------------


def test_shares_outstanding_uses_formatted_date(loaded_db):
    """period_end comes from dateFormatted, not the fiscal label like '2026-Q1'."""
    row = loaded_db.execute(
        "SELECT period_end FROM shares_outstanding WHERE ticker='AAPL'"
        " ORDER BY period_end DESC LIMIT 1"
    ).fetchone()
    assert isinstance(row[0], date)
    assert row[0] == date(2026, 3, 31)


def test_shares_outstanding_count(loaded_db):
    count = loaded_db.execute(
        "SELECT COUNT(*) FROM shares_outstanding WHERE ticker='AAPL'"
    ).fetchone()[0]
    assert count == 163


# ---------------------------------------------------------------------------
# Section: dividends
# ---------------------------------------------------------------------------


def test_dividends_declared(loaded_db):
    row = loaded_db.execute(
        "SELECT ex_date, forward_annual_dividend_rate, currency FROM dividends_declared"
        " WHERE ticker='AAPL'"
    ).fetchone()
    assert row is not None
    assert isinstance(row[0], date)
    assert row[2] == "USD"


def test_dividends_annual_count(loaded_db):
    count = loaded_db.execute(
        "SELECT COUNT(*) FROM dividends_annual WHERE ticker='AAPL'"
    ).fetchone()[0]
    assert count == 24


def test_splits(loaded_db):
    row = loaded_db.execute("SELECT split_date, factor FROM splits WHERE ticker='AAPL'").fetchone()
    assert row[0] == date(2020, 8, 31)
    assert row[1] == "4:1"


# ---------------------------------------------------------------------------
# Section: analyst snapshot
# ---------------------------------------------------------------------------


def test_daily_forward_snapshot(loaded_db):
    row = loaded_db.execute(
        "SELECT consensus_rating, target_price, n_strong_buy, eps_estimate_curr_q"
        " FROM daily_forward_snapshot WHERE ticker='AAPL'"
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(4.1042, rel=1e-3)
    assert row[1] == pytest.approx(305.2809, rel=1e-3)
    assert row[2] == 25


def test_analyst_estimates_history_count(loaded_db):
    count = loaded_db.execute(
        "SELECT COUNT(*) FROM analyst_estimates_history WHERE ticker='AAPL'"
    ).fetchone()[0]
    assert count == 39


def test_analyst_estimates_string_decimals(loaded_db):
    """String-encoded decimals in Earnings.Trend parse to DOUBLE."""
    row = loaded_db.execute(
        "SELECT eps_avg, eps_growth, revenue_avg FROM analyst_estimates_history"
        " WHERE ticker='AAPL' ORDER BY period_end DESC LIMIT 1"
    ).fetchone()
    assert isinstance(row[0], float)
    assert isinstance(row[1], float)
    assert isinstance(row[2], float)


def test_analyst_estimates_null_fields(loaded_db):
    """Null Trend fields (e.g. revenueEstimateYearAgoEps) store as NULL."""
    # The +1y entry has revenueEstimateYearAgoEps = None in the fixture
    row = loaded_db.execute(
        "SELECT revenue_year_ago FROM analyst_estimates_history"
        " WHERE ticker='AAPL' AND period='+1y'"
    ).fetchone()
    assert row is not None
    assert row[0] is None


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotency(db):
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS)
    counts_1 = {
        t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in [
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "earnings_events",
            "shares_outstanding",
            "daily_forward_snapshot",
            "analyst_estimates_history",
        ]
    }

    ingest_ticker(db, FUNDAMENTALS)
    for table, count in counts_1.items():
        count_2 = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count_2 == count, f"{table} row count changed: {count} -> {count_2}"


# ---------------------------------------------------------------------------
# Restatement
# ---------------------------------------------------------------------------


def test_restatement_updates_value(tmp_path, db):
    """Changing a BS value and re-ingesting updates the row; count stays the same."""
    from src.ingest.orchestrator import ingest_ticker

    ingest_ticker(db, FUNDAMENTALS)
    count_before = db.execute("SELECT COUNT(*) FROM balance_sheet WHERE ticker='AAPL'").fetchone()[
        0
    ]

    with FUNDAMENTALS.open() as f:
        data = json.load(f)

    bs = data["Financials"]["Balance_Sheet"]["quarterly"]
    most_recent = list(bs.keys())[0]
    original = float(bs[most_recent]["totalAssets"])
    bs[most_recent]["totalAssets"] = str(original + 1_000_000)

    restated = tmp_path / "AAPL-restated.json"
    restated.write_text(json.dumps(data))
    ingest_ticker(db, restated)

    count_after = db.execute("SELECT COUNT(*) FROM balance_sheet WHERE ticker='AAPL'").fetchone()[0]
    assert count_after == count_before

    updated = db.execute(
        "SELECT total_assets FROM balance_sheet WHERE ticker='AAPL'"
        " ORDER BY fiscal_period_end DESC LIMIT 1"
    ).fetchone()[0]
    assert updated == pytest.approx(original + 1_000_000)
