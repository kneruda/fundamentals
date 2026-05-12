"""
Thin query layer — all SQL lives here.  Page files import functions, not SQL.
"""

from pathlib import Path

import duckdb
import pandas as pd
import yaml

_ROOT = Path(__file__).parent.parent.parent
_SETTINGS_PATH = _ROOT / "config" / "settings.yml"


def _warehouse_path() -> Path:
    with _SETTINGS_PATH.open() as f:
        cfg = yaml.safe_load(f)
    return _ROOT / cfg["paths"]["warehouse"]


def open_warehouse() -> duckdb.DuckDBPyConnection:
    from src.schema.runner import open_db

    return open_db(str(_warehouse_path()))


def warehouse_mtime() -> float:
    p = _warehouse_path()
    return p.stat().st_mtime if p.exists() else 0.0


# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------

_UNIVERSE_SUMMARY_SQL = """
WITH
price_lag AS (
    SELECT ticker, date, adjusted_close,
           LAG(adjusted_close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
    FROM prices_daily
),
latest_price AS (
    SELECT pl.*
    FROM price_lag pl
    JOIN (SELECT ticker, MAX(date) AS mx FROM prices_daily GROUP BY ticker) lp
        ON pl.ticker = lp.ticker AND pl.date = lp.mx
),
latest_mult AS (
    SELECT tm.*
    FROM trailing_multiples_daily tm
    JOIN (SELECT ticker, MAX(date) AS mx FROM trailing_multiples_daily GROUP BY ticker) lm
        ON tm.ticker = lm.ticker AND tm.date = lm.mx
),
latest_snap AS (
    SELECT dfs.*
    FROM daily_forward_snapshot dfs
    JOIN (SELECT ticker, MAX(snapshot_date) AS mx FROM daily_forward_snapshot GROUP BY ticker) ls
        ON dfs.ticker = ls.ticker AND dfs.snapshot_date = ls.mx
),
latest_fund AS (
    SELECT qf.*
    FROM quarterly_fundamentals qf
    JOIN (SELECT ticker, MAX(mrq_period_end) AS mx FROM quarterly_fundamentals GROUP BY ticker) lf
        ON qf.ticker = lf.ticker AND qf.mrq_period_end = lf.mx
)
SELECT
    u.ticker,
    sm.name,
    sm.sector,
    p.adjusted_close                                                AS price,
    (p.adjusted_close / NULLIF(p.prev_close, 0) - 1) * 100        AS pct_1d,
    m.mktcap / 1e9                                                  AS mktcap_b,
    m.pe_trailing,
    CASE WHEN p.adjusted_close > 0 AND s.eps_estimate_curr_y > 0
         THEN p.adjusted_close / s.eps_estimate_curr_y             END AS pe_forward,
    m.ps_trailing,
    m.pb_trailing,
    m.ev_ebitda_trailing,
    f.quarterly_revenue_growth_yoy * 100                           AS rev_yoy_pct,
    f.quarterly_earnings_growth_yoy * 100                          AS eps_yoy_pct,
    CASE WHEN p.adjusted_close > 0 AND f.dividend_share > 0
         THEN f.dividend_share / p.adjusted_close * 100            END AS div_yield_pct,
    s.consensus_rating,
    s.target_price,
    CASE WHEN p.adjusted_close > 0 AND s.target_price IS NOT NULL
         THEN (s.target_price / p.adjusted_close - 1) * 100       END AS target_upside_pct
FROM universe u
LEFT JOIN security_master sm  ON u.ticker = sm.ticker
LEFT JOIN latest_price p      ON u.ticker = p.ticker
LEFT JOIN latest_mult m       ON u.ticker = m.ticker
LEFT JOIN latest_snap s       ON u.ticker = s.ticker
LEFT JOIN latest_fund f       ON u.ticker = f.ticker
WHERE u.active = true
ORDER BY sm.sector NULLS LAST, u.ticker
"""


def universe_summary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(_UNIVERSE_SUMMARY_SQL).df()


# ---------------------------------------------------------------------------
# Deep Dive — header
# ---------------------------------------------------------------------------

_TICKER_HEADER_SQL = """
WITH
price_lag AS (
    SELECT ticker, date, adjusted_close,
           LAG(adjusted_close) OVER (PARTITION BY ticker ORDER BY date) AS prev_close
    FROM prices_daily
    WHERE ticker = ?
),
latest_price AS (
    SELECT pl.*
    FROM price_lag pl
    JOIN (SELECT ticker, MAX(date) AS mx FROM prices_daily WHERE ticker = ? GROUP BY ticker) lp
        ON pl.ticker = lp.ticker AND pl.date = lp.mx
),
latest_mult AS (
    SELECT tm.*
    FROM trailing_multiples_daily tm
    JOIN (SELECT ticker, MAX(date) AS mx FROM trailing_multiples_daily WHERE ticker = ? GROUP BY ticker) lm
        ON tm.ticker = lm.ticker AND tm.date = lm.mx
),
next_earnings AS (
    SELECT MIN(fiscal_period_end) AS next_period
    FROM earnings_events
    WHERE ticker = ? AND eps_actual IS NULL AND fiscal_period_end > CURRENT_DATE
)
SELECT
    sm.name,
    sm.sector,
    sm.industry,
    sm.currency_code,
    p.date           AS price_date,
    p.adjusted_close AS price,
    (p.adjusted_close / NULLIF(p.prev_close, 0) - 1) * 100 AS pct_1d,
    m.mktcap / 1e9   AS mktcap_b,
    ne.next_period   AS next_period_end
FROM security_master sm
LEFT JOIN latest_price p ON sm.ticker = p.ticker
LEFT JOIN latest_mult m  ON sm.ticker = m.ticker
CROSS JOIN next_earnings ne
WHERE sm.ticker = ?
"""


def ticker_header(con: duckdb.DuckDBPyConnection, ticker: str) -> dict:
    row = con.execute(_TICKER_HEADER_SQL, [ticker] * 5).fetchone()
    if not row:
        return {}
    cols = [
        "name",
        "sector",
        "industry",
        "currency",
        "price_date",
        "price",
        "pct_1d",
        "mktcap_b",
        "next_period_end",
    ]
    return dict(zip(cols, row, strict=False))


# ---------------------------------------------------------------------------
# Deep Dive — valuation history
# ---------------------------------------------------------------------------


def valuation_history(con: duckdb.DuckDBPyConnection, ticker: str, years: int = 5) -> pd.DataFrame:
    return con.execute(
        """
        SELECT date, pe_trailing, ps_trailing, pb_trailing,
               ev_ebitda_trailing, fcf_yield * 100 AS fcf_yield_pct
        FROM trailing_multiples_daily
        WHERE ticker = ?
          AND date >= CURRENT_DATE - INTERVAL (? * 365) DAY
        ORDER BY date
    """,
        [ticker, years],
    ).df()


def valuation_stats(history: pd.DataFrame) -> pd.DataFrame:
    """Current value vs. own median and percentile from a valuation history DataFrame.

    Takes the output of valuation_history() so no extra query is needed.
    Percentile rank = fraction of historical observations below the current value.
    """
    multiples = [
        ("pe_trailing", "P/E"),
        ("ps_trailing", "P/S"),
        ("pb_trailing", "P/B"),
        ("ev_ebitda_trailing", "EV/EBITDA"),
    ]
    rows = []
    for col, name in multiples:
        if col not in history.columns:
            continue
        values = history[col].dropna()
        if len(values) < 2:
            continue
        current = float(values.iloc[-1])
        median = float(values.median())
        pct_rank = float((values < current).mean() * 100)
        rows.append({"metric": name, "current": current, "median": median, "pct_rank": pct_rank})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Deep Dive — profitability & growth
# ---------------------------------------------------------------------------


def quarterly_metrics(con: duckdb.DuckDBPyConnection, ticker: str, n: int = 12) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
            stmt.fiscal_period_end,
            stmt.total_revenue / 1e9                                          AS revenue_b,
            stmt.gross_profit / NULLIF(stmt.total_revenue, 0) * 100          AS gross_margin_pct,
            stmt.operating_income / NULLIF(stmt.total_revenue, 0) * 100      AS operating_margin_pct,
            stmt.net_income / NULLIF(stmt.total_revenue, 0) * 100            AS net_margin_pct,
            cf.free_cash_flow / NULLIF(stmt.total_revenue, 0) * 100          AS fcf_margin_pct,
            stmt.net_income / NULLIF(bs.total_stockholder_equity, 0) * 100   AS roe_pct
        FROM income_statement stmt
        LEFT JOIN cash_flow cf
            ON stmt.ticker = cf.ticker AND stmt.fiscal_period_end = cf.fiscal_period_end
        LEFT JOIN balance_sheet bs
            ON stmt.ticker = bs.ticker AND stmt.fiscal_period_end = bs.fiscal_period_end
        WHERE stmt.ticker = ? AND stmt.total_revenue IS NOT NULL
        ORDER BY stmt.fiscal_period_end DESC
        LIMIT ?
    """,
        [ticker, n],
    ).df()


# ---------------------------------------------------------------------------
# Deep Dive — analyst view
# ---------------------------------------------------------------------------


def latest_analyst_snapshot(con: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    row = con.execute(
        """
        SELECT snapshot_date, consensus_rating, target_price,
               n_strong_buy, n_buy, n_hold, n_sell, n_strong_sell,
               eps_estimate_curr_y, eps_estimate_next_y
        FROM daily_forward_snapshot
        WHERE ticker = ?
        ORDER BY snapshot_date DESC
        LIMIT 1
    """,
        [ticker],
    ).fetchone()
    if not row:
        return None
    cols = [
        "snapshot_date",
        "consensus_rating",
        "target_price",
        "n_strong_buy",
        "n_buy",
        "n_hold",
        "n_sell",
        "n_strong_sell",
        "eps_est_curr_y",
        "eps_est_next_y",
    ]
    return dict(zip(cols, row, strict=False))


# ---------------------------------------------------------------------------
# Deep Dive — earnings history
# ---------------------------------------------------------------------------


def earnings_history(con: duckdb.DuckDBPyConnection, ticker: str) -> pd.DataFrame:
    return con.execute(
        """
        WITH price_next AS (
            SELECT ticker, date, adjusted_close,
                   LEAD(adjusted_close) OVER (PARTITION BY ticker ORDER BY date) AS next_close
            FROM prices_daily
        )
        SELECT
            ee.fiscal_period_end,
            ee.report_date,
            ee.eps_estimate,
            ee.eps_actual,
            ee.surprise_percent,
            (pn.next_close / NULLIF(pn.adjusted_close, 0) - 1) * 100 AS next_day_return_pct
        FROM earnings_events ee
        LEFT JOIN price_next pn ON ee.ticker = pn.ticker AND pn.date = ee.report_date
        WHERE ee.ticker = ? AND ee.eps_actual IS NOT NULL
        ORDER BY ee.fiscal_period_end DESC
        LIMIT 16
    """,
        [ticker],
    ).df()


# ---------------------------------------------------------------------------
# Deep Dive — capital returns
# ---------------------------------------------------------------------------


def latest_dividends(con: duckdb.DuckDBPyConnection, ticker: str) -> dict | None:
    row = con.execute(
        """
        SELECT forward_annual_dividend_rate, forward_annual_dividend_yield,
               payout_ratio, ex_date, pay_date
        FROM dividends_declared
        WHERE ticker = ?
        ORDER BY ex_date DESC
        LIMIT 1
    """,
        [ticker],
    ).fetchone()
    if not row:
        return None
    cols = ["fwd_div_rate", "fwd_div_yield", "payout_ratio", "ex_date", "pay_date"]
    return dict(zip(cols, row, strict=False))


def dividend_annual_history(con: duckdb.DuckDBPyConnection, ticker: str) -> pd.DataFrame:
    return con.execute(
        """
        SELECT year, count AS n_dividends
        FROM dividends_annual
        WHERE ticker = ?
        ORDER BY year DESC
        LIMIT 10
    """,
        [ticker],
    ).df()


# ---------------------------------------------------------------------------
# Deep Dive — financial statements
# ---------------------------------------------------------------------------


def income_statement_history(
    con: duckdb.DuckDBPyConnection, ticker: str, n: int = 8
) -> pd.DataFrame:
    return con.execute(
        """
        SELECT fiscal_period_end, total_revenue, gross_profit, ebitda,
               operating_income, net_income, interest_expense,
               research_development
        FROM income_statement
        WHERE ticker = ?
        ORDER BY fiscal_period_end DESC
        LIMIT ?
    """,
        [ticker, n],
    ).df()


def balance_sheet_history(con: duckdb.DuckDBPyConnection, ticker: str, n: int = 8) -> pd.DataFrame:
    return con.execute(
        """
        SELECT fiscal_period_end,
               cash_and_short_term_investments,
               total_current_assets, total_assets,
               total_current_liabilities,
               long_term_debt_total, short_term_debt,
               total_stockholder_equity,
               (COALESCE(long_term_debt_total, 0) + COALESCE(short_term_debt, 0)
                - COALESCE(cash_and_short_term_investments, 0)) AS net_debt
        FROM balance_sheet
        WHERE ticker = ?
        ORDER BY fiscal_period_end DESC
        LIMIT ?
    """,
        [ticker, n],
    ).df()


def cash_flow_history(con: duckdb.DuckDBPyConnection, ticker: str, n: int = 8) -> pd.DataFrame:
    return con.execute(
        """
        SELECT fiscal_period_end,
               total_cash_from_operating_activities, capital_expenditures,
               free_cash_flow, dividends_paid, net_borrowings
        FROM cash_flow
        WHERE ticker = ?
        ORDER BY fiscal_period_end DESC
        LIMIT ?
    """,
        [ticker, n],
    ).df()


# ---------------------------------------------------------------------------
# Universe management
# ---------------------------------------------------------------------------


def universe_management_list(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("""
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            u.added_at::DATE     AS added_at,
            sm.loaded_at::DATE   AS last_loaded,
            u.active,
            u.notes
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        ORDER BY u.active DESC, u.ticker
    """).df()


def active_tickers(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute("SELECT ticker FROM universe WHERE active = true ORDER BY ticker").fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Phase 6 — snapshot coverage
# ---------------------------------------------------------------------------


def snapshot_coverage(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Days of analyst snapshot history per active ticker."""
    return con.execute("""
        SELECT
            u.ticker,
            MIN(dfs.snapshot_date)::VARCHAR                              AS first_snapshot,
            MAX(dfs.snapshot_date)::VARCHAR                              AS last_snapshot,
            COUNT(DISTINCT dfs.snapshot_date)                            AS n_days,
            (CURRENT_DATE - MAX(dfs.snapshot_date))                      AS days_since_last
        FROM universe u
        LEFT JOIN daily_forward_snapshot dfs ON u.ticker = dfs.ticker
        WHERE u.active = true
        GROUP BY u.ticker
        ORDER BY u.ticker
    """).df()
