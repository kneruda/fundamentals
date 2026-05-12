import duckdb

_TTM_EPS = """
CREATE OR REPLACE VIEW ttm_eps AS
WITH ordered AS (
    SELECT
        ticker,
        fiscal_period_end,
        report_date,
        eps_actual,
        SUM(eps_actual) OVER (
            PARTITION BY ticker ORDER BY fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_eps,
        COUNT(eps_actual) OVER (
            PARTITION BY ticker ORDER BY fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS n_quarters
    FROM earnings_events
    WHERE eps_actual IS NOT NULL AND report_date IS NOT NULL
)
SELECT ticker, report_date, ttm_eps
FROM ordered
WHERE n_quarters = 4
"""

_TTM_REVENUE = """
CREATE OR REPLACE VIEW ttm_revenue AS
WITH ordered AS (
    SELECT
        stmt.ticker,
        stmt.fiscal_period_end,
        ee.report_date,
        stmt.total_revenue,
        SUM(stmt.total_revenue) OVER (
            PARTITION BY stmt.ticker ORDER BY stmt.fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_revenue,
        COUNT(stmt.total_revenue) OVER (
            PARTITION BY stmt.ticker ORDER BY stmt.fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS n_quarters
    FROM income_statement stmt
    LEFT JOIN earnings_events ee
        ON stmt.ticker = ee.ticker AND stmt.fiscal_period_end = ee.fiscal_period_end
    WHERE stmt.total_revenue IS NOT NULL
)
SELECT ticker, report_date, ttm_revenue
FROM ordered
WHERE n_quarters = 4 AND report_date IS NOT NULL
"""

_TTM_EBITDA = """
CREATE OR REPLACE VIEW ttm_ebitda AS
WITH ordered AS (
    SELECT
        stmt.ticker,
        stmt.fiscal_period_end,
        ee.report_date,
        stmt.ebitda,
        SUM(stmt.ebitda) OVER (
            PARTITION BY stmt.ticker ORDER BY stmt.fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_ebitda,
        COUNT(stmt.ebitda) OVER (
            PARTITION BY stmt.ticker ORDER BY stmt.fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS n_quarters
    FROM income_statement stmt
    LEFT JOIN earnings_events ee
        ON stmt.ticker = ee.ticker AND stmt.fiscal_period_end = ee.fiscal_period_end
    WHERE stmt.ebitda IS NOT NULL
)
SELECT ticker, report_date, ttm_ebitda
FROM ordered
WHERE n_quarters = 4 AND report_date IS NOT NULL
"""

_TTM_FCF = """
CREATE OR REPLACE VIEW ttm_fcf AS
WITH ordered AS (
    SELECT
        cf.ticker,
        cf.fiscal_period_end,
        ee.report_date,
        cf.free_cash_flow,
        SUM(cf.free_cash_flow) OVER (
            PARTITION BY cf.ticker ORDER BY cf.fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS ttm_fcf,
        COUNT(cf.free_cash_flow) OVER (
            PARTITION BY cf.ticker ORDER BY cf.fiscal_period_end
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) AS n_quarters
    FROM cash_flow cf
    LEFT JOIN earnings_events ee
        ON cf.ticker = ee.ticker AND cf.fiscal_period_end = ee.fiscal_period_end
    WHERE cf.free_cash_flow IS NOT NULL
)
SELECT ticker, report_date, ttm_fcf
FROM ordered
WHERE n_quarters = 4 AND report_date IS NOT NULL
"""


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    for sql in (_TTM_EPS, _TTM_REVENUE, _TTM_EBITDA, _TTM_FCF):
        con.execute(sql)
