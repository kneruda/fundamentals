import duckdb

# Net debt formula (see PLAN.md open questions):
#   long_term_debt_total + short_term_debt - cash_and_short_term_investments
# COALESCE to 0 so a missing component doesn't null the whole EV.
_TRAILING_MULTIPLES = """
CREATE OR REPLACE VIEW trailing_multiples_daily AS
SELECT
    p.ticker,
    p.date,
    p.adjusted_close,
    s.shares,
    p.adjusted_close * s.shares                                    AS mktcap,
    CASE WHEN eps.ttm_eps  > 0
         THEN p.adjusted_close / eps.ttm_eps                       END AS pe_trailing,
    CASE WHEN rev.ttm_revenue > 0 AND s.shares IS NOT NULL
         THEN (p.adjusted_close * s.shares) / rev.ttm_revenue      END AS ps_trailing,
    CASE WHEN bs.total_stockholder_equity > 0 AND s.shares > 0
         THEN p.adjusted_close / (bs.total_stockholder_equity / s.shares) END AS pb_trailing,
    CASE WHEN ebi.ttm_ebitda > 0 AND s.shares IS NOT NULL
         THEN (
             p.adjusted_close * s.shares
             + COALESCE(bs.long_term_debt_total, 0)
             + COALESCE(bs.short_term_debt, 0)
             - COALESCE(bs.cash_and_short_term_investments, 0)
         ) / ebi.ttm_ebitda                                        END AS ev_ebitda_trailing,
    CASE WHEN s.shares IS NOT NULL AND p.adjusted_close * s.shares > 0
         THEN fcf.ttm_fcf / (p.adjusted_close * s.shares)         END AS fcf_yield
FROM prices_daily p
ASOF LEFT JOIN shares_outstanding  s   ON p.ticker = s.ticker   AND p.date >= s.period_end
ASOF LEFT JOIN ttm_eps             eps ON p.ticker = eps.ticker  AND p.date >= eps.report_date
ASOF LEFT JOIN ttm_revenue         rev ON p.ticker = rev.ticker  AND p.date >= rev.report_date
ASOF LEFT JOIN ttm_ebitda          ebi ON p.ticker = ebi.ticker  AND p.date >= ebi.report_date
ASOF LEFT JOIN ttm_fcf             fcf ON p.ticker = fcf.ticker  AND p.date >= fcf.report_date
ASOF LEFT JOIN balance_sheet       bs  ON p.ticker = bs.ticker   AND p.date >= bs.report_date
"""


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_TRAILING_MULTIPLES)
