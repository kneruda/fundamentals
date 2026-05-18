import duckdb

_SIZE_LATEST = """
CREATE OR REPLACE VIEW universe_size_latest AS
WITH recent AS (
    SELECT ticker, close, adjusted_close, volume,
           ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
    FROM prices_daily
),
adtv AS (
    SELECT ticker, AVG(close * volume) / 1e6 AS adtv_20d_m
    FROM recent
    WHERE rn <= 20
    GROUP BY ticker
),
latest_price AS (
    SELECT ticker, adjusted_close
    FROM recent
    WHERE rn = 1
),
latest_shares AS (
    SELECT so.ticker, so.shares
    FROM shares_outstanding so
    JOIN (
        SELECT ticker, MAX(period_end) AS mx
        FROM shares_outstanding
        GROUP BY ticker
    ) ls ON so.ticker = ls.ticker AND so.period_end = ls.mx
)
SELECT
    lp.ticker,
    lp.adjusted_close * ls.shares / 1e9 AS mktcap_b,
    ad.adtv_20d_m
FROM latest_price lp
LEFT JOIN latest_shares ls ON lp.ticker = ls.ticker
LEFT JOIN adtv ad           ON lp.ticker = ad.ticker
"""


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_SIZE_LATEST)
