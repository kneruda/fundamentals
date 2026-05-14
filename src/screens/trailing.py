"""Trailing fundamental screens — parameterized filters over the active universe."""

import duckdb
import pandas as pd


def screen_absolute_valuation(
    con: duckdb.DuckDBPyConnection,
    *,
    max_pe: float | None = None,
    max_ps: float | None = None,
    max_pb: float | None = None,
    max_ev_ebitda: float | None = None,
    min_fcf_yield: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Active tickers passing absolute multiple thresholds."""
    df = con.execute("""
        WITH latest_mult AS (
            SELECT tm.*
            FROM trailing_multiples_daily tm
            JOIN (SELECT ticker, MAX(date) AS mx FROM trailing_multiples_daily GROUP BY ticker) lm
                ON tm.ticker = lm.ticker AND tm.date = lm.mx
        )
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            m.pe_trailing,
            m.ps_trailing,
            m.pb_trailing,
            m.ev_ebitda_trailing,
            m.fcf_yield * 100 AS fcf_yield_pct
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_mult m      ON u.ticker = m.ticker
        WHERE u.active = true
        ORDER BY sm.sector NULLS LAST, u.ticker
    """).df()
    if max_pe is not None:
        df = df[df["pe_trailing"].notna() & (df["pe_trailing"] <= max_pe)]
    if max_ps is not None:
        df = df[df["ps_trailing"].notna() & (df["ps_trailing"] <= max_ps)]
    if max_pb is not None:
        df = df[df["pb_trailing"].notna() & (df["pb_trailing"] <= max_pb)]
    if max_ev_ebitda is not None:
        df = df[df["ev_ebitda_trailing"].notna() & (df["ev_ebitda_trailing"] <= max_ev_ebitda)]
    if min_fcf_yield is not None:
        df = df[df["fcf_yield_pct"].notna() & (df["fcf_yield_pct"] >= min_fcf_yield)]
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)


def screen_relative_history(
    con: duckdb.DuckDBPyConnection,
    *,
    years: int = 5,
    max_pe_rank: float | None = None,
    max_ev_rank: float | None = None,
    max_ps_rank: float | None = None,
    min_history_days: int = 0,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers whose current multiples are cheap vs. their own history.

    Percentile rank: 0 = historical low, 100 = historical high.
    Lower rank means cheaper relative to own history.
    """
    df = con.execute(
        """
        WITH history AS (
            SELECT ticker, date, pe_trailing, ev_ebitda_trailing, ps_trailing
            FROM trailing_multiples_daily
            WHERE date >= CURRENT_DATE - INTERVAL (? * 365) DAY
        ),
        ranked AS (
            SELECT *,
                   PERCENT_RANK() OVER (PARTITION BY ticker ORDER BY pe_trailing)       AS pe_rank,
                   PERCENT_RANK() OVER (PARTITION BY ticker ORDER BY ev_ebitda_trailing) AS ev_rank,
                   PERCENT_RANK() OVER (PARTITION BY ticker ORDER BY ps_trailing)        AS ps_rank,
                   COUNT(*) OVER (PARTITION BY ticker)                                   AS n_obs
            FROM history
        ),
        latest AS (
            SELECT r.*
            FROM ranked r
            JOIN (SELECT ticker, MAX(date) AS mx FROM history GROUP BY ticker) lh
                ON r.ticker = lh.ticker AND r.date = lh.mx
        )
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            l.pe_trailing,
            l.pe_rank * 100     AS pe_pct_rank,
            l.ev_ebitda_trailing,
            l.ev_rank * 100     AS ev_pct_rank,
            l.ps_trailing,
            l.ps_rank * 100     AS ps_pct_rank,
            l.n_obs             AS history_days
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest l           ON u.ticker = l.ticker
        WHERE u.active = true
        ORDER BY l.pe_rank NULLS LAST, u.ticker
        """,
        [years],
    ).df()
    if min_history_days > 0:
        df = df[df["history_days"].notna() & (df["history_days"] >= min_history_days)]
    if max_pe_rank is not None:
        df = df[df["pe_pct_rank"].notna() & (df["pe_pct_rank"] <= max_pe_rank)]
    if max_ev_rank is not None:
        df = df[df["ev_pct_rank"].notna() & (df["ev_pct_rank"] <= max_ev_rank)]
    if max_ps_rank is not None:
        df = df[df["ps_pct_rank"].notna() & (df["ps_pct_rank"] <= max_ps_rank)]
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)


def screen_growth(
    con: duckdb.DuckDBPyConnection,
    *,
    min_rev_yoy: float | None = None,
    min_eps_yoy: float | None = None,
    require_acceleration: bool = False,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers with strong revenue/EPS growth and optional acceleration filter."""
    df = con.execute("""
        WITH latest_fund AS (
            SELECT qf.*
            FROM quarterly_fundamentals qf
            JOIN (SELECT ticker, MAX(mrq_period_end) AS mx FROM quarterly_fundamentals GROUP BY ticker) lf
                ON qf.ticker = lf.ticker AND qf.mrq_period_end = lf.mx
        ),
        q_growth AS (
            SELECT ticker, mrq_period_end, quarterly_revenue_growth_yoy,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY mrq_period_end DESC) AS rn
            FROM quarterly_fundamentals
            WHERE quarterly_revenue_growth_yoy IS NOT NULL
        ),
        accel AS (
            SELECT ticker,
                   MAX(CASE WHEN rn = 1 THEN quarterly_revenue_growth_yoy END) AS g1,
                   MAX(CASE WHEN rn = 2 THEN quarterly_revenue_growth_yoy END) AS g2,
                   MAX(CASE WHEN rn = 3 THEN quarterly_revenue_growth_yoy END) AS g3,
                   MAX(CASE WHEN rn = 4 THEN quarterly_revenue_growth_yoy END) AS g4
            FROM q_growth
            WHERE rn <= 4
            GROUP BY ticker
        )
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            f.quarterly_revenue_growth_yoy * 100  AS rev_yoy_pct,
            f.quarterly_earnings_growth_yoy * 100 AS eps_yoy_pct,
            a.g1 * 100 AS g1_pct,
            a.g2 * 100 AS g2_pct,
            a.g3 * 100 AS g3_pct,
            a.g4 * 100 AS g4_pct,
            (a.g1 IS NOT NULL AND a.g2 IS NOT NULL AND a.g3 IS NOT NULL AND a.g4 IS NOT NULL
             AND a.g1 > a.g2 AND a.g2 > a.g3 AND a.g3 > a.g4) AS is_accelerating
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_fund f      ON u.ticker = f.ticker
        LEFT JOIN accel a            ON u.ticker = a.ticker
        WHERE u.active = true
        ORDER BY f.quarterly_revenue_growth_yoy DESC NULLS LAST, u.ticker
    """).df()
    if min_rev_yoy is not None:
        df = df[df["rev_yoy_pct"].notna() & (df["rev_yoy_pct"] >= min_rev_yoy)]
    if min_eps_yoy is not None:
        df = df[df["eps_yoy_pct"].notna() & (df["eps_yoy_pct"] >= min_eps_yoy)]
    if require_acceleration:
        df = df[df["is_accelerating"] == True]  # noqa: E712
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)


def screen_quality(
    con: duckdb.DuckDBPyConnection,
    *,
    min_roe: float | None = None,
    min_roic: float | None = None,
    min_gross_margin: float | None = None,
    min_fcf_conversion: float | None = None,
    require_margin_expansion: bool = False,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers with high returns, wide margins, and strong FCF conversion.

    ROIC = TTM operating income / (equity + LT debt + ST debt).
    FCF conversion = TTM FCF / TTM net income * 100.
    Margin expansion: latest quarter gross margin > same quarter one year prior.
    """
    df = con.execute("""
        WITH latest_fund AS (
            SELECT qf.ticker, qf.return_on_equity_ttm, qf.operating_margin_ttm
            FROM quarterly_fundamentals qf
            JOIN (SELECT ticker, MAX(mrq_period_end) AS mx FROM quarterly_fundamentals GROUP BY ticker) lf
                ON qf.ticker = lf.ticker AND qf.mrq_period_end = lf.mx
        ),
        latest_bs AS (
            SELECT bs.ticker, bs.total_stockholder_equity,
                   COALESCE(bs.long_term_debt_total, 0) AS ltd,
                   COALESCE(bs.short_term_debt, 0)       AS std
            FROM balance_sheet bs
            JOIN (SELECT ticker, MAX(fiscal_period_end) AS mx FROM balance_sheet GROUP BY ticker) lb
                ON bs.ticker = lb.ticker AND bs.fiscal_period_end = lb.mx
        ),
        ttm_op AS (
            SELECT ticker, SUM(operating_income) AS ttm_op_income
            FROM (
                SELECT ticker, operating_income,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fiscal_period_end DESC) AS rn
                FROM income_statement
                WHERE operating_income IS NOT NULL
            )
            WHERE rn <= 4
            GROUP BY ticker
        ),
        latest_fcf AS (
            SELECT tf.ticker, tf.ttm_fcf
            FROM ttm_fcf tf
            JOIN (SELECT ticker, MAX(report_date) AS mx FROM ttm_fcf GROUP BY ticker) lf
                ON tf.ticker = lf.ticker AND tf.report_date = lf.mx
        ),
        ttm_ni AS (
            SELECT ticker, SUM(net_income) AS ttm_net_income
            FROM (
                SELECT ticker, net_income,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fiscal_period_end DESC) AS rn
                FROM income_statement
                WHERE net_income IS NOT NULL
            )
            WHERE rn <= 4
            GROUP BY ticker
        ),
        margin_hist AS (
            SELECT ticker, fiscal_period_end,
                   gross_profit / NULLIF(total_revenue, 0) AS gross_margin,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fiscal_period_end DESC) AS rn
            FROM income_statement
            WHERE total_revenue IS NOT NULL AND gross_profit IS NOT NULL
        ),
        margin_cmp AS (
            SELECT m1.ticker,
                   m1.gross_margin AS gross_margin_curr,
                   m5.gross_margin AS gross_margin_prior,
                   (m5.gross_margin IS NOT NULL AND m1.gross_margin > m5.gross_margin) AS margin_expanding
            FROM margin_hist m1
            LEFT JOIN margin_hist m5 ON m1.ticker = m5.ticker AND m5.rn = 5
            WHERE m1.rn = 1
        )
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            f.return_on_equity_ttm * 100                                             AS roe_pct,
            CASE WHEN (bs.total_stockholder_equity + bs.ltd + bs.std) > 0
                 THEN op.ttm_op_income / (bs.total_stockholder_equity + bs.ltd + bs.std) * 100
                 END                                                                  AS roic_pct,
            mc.gross_margin_curr * 100                                               AS gross_margin_pct,
            f.operating_margin_ttm * 100                                             AS op_margin_pct,
            CASE WHEN ni.ttm_net_income > 0
                 THEN fcf.ttm_fcf / ni.ttm_net_income * 100
                 END                                                                  AS fcf_conversion_pct,
            mc.margin_expanding
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_fund f      ON u.ticker = f.ticker
        LEFT JOIN latest_bs bs       ON u.ticker = bs.ticker
        LEFT JOIN ttm_op op          ON u.ticker = op.ticker
        LEFT JOIN latest_fcf fcf     ON u.ticker = fcf.ticker
        LEFT JOIN ttm_ni ni          ON u.ticker = ni.ticker
        LEFT JOIN margin_cmp mc      ON u.ticker = mc.ticker
        WHERE u.active = true
        ORDER BY f.return_on_equity_ttm DESC NULLS LAST, u.ticker
    """).df()
    if min_roe is not None:
        df = df[df["roe_pct"].notna() & (df["roe_pct"] >= min_roe)]
    if min_roic is not None:
        df = df[df["roic_pct"].notna() & (df["roic_pct"] >= min_roic)]
    if min_gross_margin is not None:
        df = df[df["gross_margin_pct"].notna() & (df["gross_margin_pct"] >= min_gross_margin)]
    if min_fcf_conversion is not None:
        df = df[df["fcf_conversion_pct"].notna() & (df["fcf_conversion_pct"] >= min_fcf_conversion)]
    if require_margin_expansion:
        df = df[df["margin_expanding"] == True]  # noqa: E712
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)


def screen_balance_sheet(
    con: duckdb.DuckDBPyConnection,
    *,
    max_net_debt_ebitda: float | None = None,
    min_interest_coverage: float | None = None,
    min_current_ratio: float | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Tickers with strong balance sheets — low leverage, solid coverage, ample liquidity."""
    df = con.execute("""
        WITH latest_bs AS (
            SELECT bs.ticker,
                   bs.total_current_assets,
                   bs.total_current_liabilities,
                   (COALESCE(bs.long_term_debt_total, 0) + COALESCE(bs.short_term_debt, 0)
                    - COALESCE(bs.cash_and_short_term_investments, 0)) AS net_debt
            FROM balance_sheet bs
            JOIN (SELECT ticker, MAX(fiscal_period_end) AS mx FROM balance_sheet GROUP BY ticker) lb
                ON bs.ticker = lb.ticker AND bs.fiscal_period_end = lb.mx
        ),
        latest_ebi AS (
            SELECT te.ticker, te.ttm_ebitda
            FROM ttm_ebitda te
            JOIN (SELECT ticker, MAX(report_date) AS mx FROM ttm_ebitda GROUP BY ticker) le
                ON te.ticker = le.ticker AND te.report_date = le.mx
        ),
        ttm_int AS (
            SELECT ticker, SUM(ABS(interest_expense)) AS ttm_interest
            FROM (
                SELECT ticker, interest_expense,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY fiscal_period_end DESC) AS rn
                FROM income_statement
                WHERE interest_expense IS NOT NULL AND interest_expense != 0
            )
            WHERE rn <= 4
            GROUP BY ticker
        )
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            bs.net_debt / 1e9                                                     AS net_debt_b,
            CASE WHEN ei.ttm_ebitda > 0
                 THEN bs.net_debt / ei.ttm_ebitda                                 END AS net_debt_ebitda,
            CASE WHEN ti.ttm_interest > 0
                 THEN ei.ttm_ebitda / ti.ttm_interest                             END AS interest_coverage,
            bs.total_current_assets / NULLIF(bs.total_current_liabilities, 0)     AS current_ratio
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_bs bs       ON u.ticker = bs.ticker
        LEFT JOIN latest_ebi ei      ON u.ticker = ei.ticker
        LEFT JOIN ttm_int ti         ON u.ticker = ti.ticker
        WHERE u.active = true
        ORDER BY net_debt_ebitda NULLS LAST, u.ticker
    """).df()
    if max_net_debt_ebitda is not None:
        df = df[df["net_debt_ebitda"].notna() & (df["net_debt_ebitda"] <= max_net_debt_ebitda)]
    if min_interest_coverage is not None:
        df = df[
            df["interest_coverage"].notna() & (df["interest_coverage"] >= min_interest_coverage)
        ]
    if min_current_ratio is not None:
        df = df[df["current_ratio"].notna() & (df["current_ratio"] >= min_current_ratio)]
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)


def screen_income(
    con: duckdb.DuckDBPyConnection,
    *,
    min_yield: float | None = None,
    max_payout: float | None = None,
    min_div_years: int | None = None,
    display_filter: list[str] | None = None,
) -> pd.DataFrame:
    """Dividend payers with sufficient yield, sustainable payout, and history."""
    df = con.execute("""
        WITH latest_div AS (
            SELECT dd.ticker, dd.forward_annual_dividend_yield, dd.payout_ratio
            FROM dividends_declared dd
            JOIN (SELECT ticker, MAX(ex_date) AS mx FROM dividends_declared GROUP BY ticker) ld
                ON dd.ticker = ld.ticker AND dd.ex_date = ld.mx
        ),
        div_years AS (
            SELECT ticker, COUNT(DISTINCT year) AS n_div_years
            FROM dividends_annual
            GROUP BY ticker
        )
        SELECT
            u.ticker,
            sm.name,
            sm.sector,
            d.forward_annual_dividend_yield * 100  AS div_yield_pct,
            d.payout_ratio * 100                   AS payout_ratio_pct,
            dy.n_div_years
        FROM universe u
        LEFT JOIN security_master sm ON u.ticker = sm.ticker
        LEFT JOIN latest_div d       ON u.ticker = d.ticker
        LEFT JOIN div_years dy       ON u.ticker = dy.ticker
        WHERE u.active = true
        ORDER BY d.forward_annual_dividend_yield DESC NULLS LAST, u.ticker
    """).df()
    if min_yield is not None:
        df = df[df["div_yield_pct"].notna() & (df["div_yield_pct"] >= min_yield)]
    if max_payout is not None:
        df = df[df["payout_ratio_pct"].notna() & (df["payout_ratio_pct"] <= max_payout)]
    if min_div_years is not None:
        df = df[df["n_div_years"].notna() & (df["n_div_years"] >= min_div_years)]
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)]
    return df.reset_index(drop=True)
