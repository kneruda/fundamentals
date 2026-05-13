"""Sector aggregate screens."""

import duckdb
import pandas as pd


def sector_summary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Median trailing multiples, growth, and dividend yield per sector for active universe."""
    return con.execute("""
        WITH latest_mult AS (
            SELECT tm.*
            FROM trailing_multiples_daily tm
            JOIN (SELECT ticker, MAX(date) AS mx FROM trailing_multiples_daily GROUP BY ticker) lm
                ON tm.ticker = lm.ticker AND tm.date = lm.mx
        ),
        latest_fund AS (
            SELECT qf.*
            FROM quarterly_fundamentals qf
            JOIN (SELECT ticker, MAX(mrq_period_end) AS mx FROM quarterly_fundamentals GROUP BY ticker) lf
                ON qf.ticker = lf.ticker AND qf.mrq_period_end = lf.mx
        ),
        latest_div AS (
            SELECT dd.ticker, dd.forward_annual_dividend_yield
            FROM dividends_declared dd
            JOIN (SELECT ticker, MAX(ex_date) AS mx FROM dividends_declared GROUP BY ticker) ld
                ON dd.ticker = ld.ticker AND dd.ex_date = ld.mx
        )
        SELECT
            COALESCE(sm.gic_sector, sm.sector, 'Unknown') AS sector,
            COUNT(*) AS n_tickers,
            MEDIAN(m.pe_trailing)                              AS median_pe,
            MEDIAN(m.ps_trailing)                              AS median_ps,
            MEDIAN(m.pb_trailing)                              AS median_pb,
            MEDIAN(m.ev_ebitda_trailing)                       AS median_ev_ebitda,
            MEDIAN(m.fcf_yield * 100)                          AS median_fcf_yield_pct,
            MEDIAN(f.quarterly_revenue_growth_yoy * 100)       AS median_rev_yoy_pct,
            MEDIAN(f.quarterly_earnings_growth_yoy * 100)      AS median_eps_yoy_pct,
            MEDIAN(d.forward_annual_dividend_yield * 100)      AS median_div_yield_pct
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_mult m      ON u.ticker = m.ticker
        LEFT JOIN latest_fund f      ON u.ticker = f.ticker
        LEFT JOIN latest_div d       ON u.ticker = d.ticker
        WHERE u.active = true
        GROUP BY COALESCE(sm.gic_sector, sm.sector, 'Unknown')
        ORDER BY sector
    """).df()


def sector_constituents(con: duckdb.DuckDBPyConnection, sector: str) -> pd.DataFrame:
    """Individual ticker metrics for a sector."""
    return con.execute("""
        WITH latest_mult AS (
            SELECT tm.*
            FROM trailing_multiples_daily tm
            JOIN (SELECT ticker, MAX(date) AS mx FROM trailing_multiples_daily GROUP BY ticker) lm
                ON tm.ticker = lm.ticker AND tm.date = lm.mx
        ),
        latest_fund AS (
            SELECT qf.*
            FROM quarterly_fundamentals qf
            JOIN (SELECT ticker, MAX(mrq_period_end) AS mx FROM quarterly_fundamentals GROUP BY ticker) lf
                ON qf.ticker = lf.ticker AND qf.mrq_period_end = lf.mx
        ),
        latest_price AS (
            SELECT pd.ticker, pd.adjusted_close
            FROM prices_daily pd
            JOIN (SELECT ticker, MAX(date) AS mx FROM prices_daily GROUP BY ticker) lp
                ON pd.ticker = lp.ticker AND pd.date = lp.mx
        ),
        latest_div AS (
            SELECT dd.ticker, dd.forward_annual_dividend_yield
            FROM dividends_declared dd
            JOIN (SELECT ticker, MAX(ex_date) AS mx FROM dividends_declared GROUP BY ticker) ld
                ON dd.ticker = ld.ticker AND dd.ex_date = ld.mx
        )
        SELECT
            u.ticker,
            sm.name,
            COALESCE(sm.gic_sub_industry, sm.industry, 'Unknown') AS sub_industry,
            p.adjusted_close                                        AS price,
            m.mktcap / 1e9                                          AS mktcap_b,
            m.pe_trailing,
            m.ps_trailing,
            m.pb_trailing,
            m.ev_ebitda_trailing,
            m.fcf_yield * 100                                       AS fcf_yield_pct,
            f.quarterly_revenue_growth_yoy * 100                    AS rev_yoy_pct,
            f.quarterly_earnings_growth_yoy * 100                   AS eps_yoy_pct,
            d.forward_annual_dividend_yield * 100                   AS div_yield_pct
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_mult m      ON u.ticker = m.ticker
        LEFT JOIN latest_fund f      ON u.ticker = f.ticker
        LEFT JOIN latest_price p     ON u.ticker = p.ticker
        LEFT JOIN latest_div d       ON u.ticker = d.ticker
        WHERE u.active = true
          AND COALESCE(sm.gic_sector, sm.sector, 'Unknown') = ?
        ORDER BY sm.name NULLS LAST, u.ticker
    """, [sector]).df()
