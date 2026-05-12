from pathlib import Path

import duckdb
import yaml

_SETTINGS_PATH = Path(__file__).parent.parent.parent / "config" / "settings.yml"


def _benchmark_ticker() -> str:
    with _SETTINGS_PATH.open() as f:
        cfg = yaml.safe_load(f)
    return cfg.get("benchmark", {}).get("ticker", "SPY.US")


def _build_sql(benchmark: str) -> str:
    return f"""
CREATE OR REPLACE VIEW technicals_daily AS
WITH log_returns AS (
    SELECT
        ticker,
        date,
        adjusted_close,
        LN(adjusted_close / LAG(adjusted_close) OVER (PARTITION BY ticker ORDER BY date)) AS log_return
    FROM prices_daily
),
bm_returns AS (
    SELECT date, log_return AS bm_return
    FROM log_returns
    WHERE ticker = '{benchmark}'
),
joined AS (
    SELECT
        lr.ticker,
        lr.date,
        lr.adjusted_close,
        lr.log_return,
        bm.bm_return
    FROM log_returns lr
    LEFT JOIN bm_returns bm USING (date)
    WHERE lr.ticker <> '{benchmark}'
)
SELECT
    ticker,
    date,
    adjusted_close,
    AVG(adjusted_close)  OVER w20  AS ma_20,
    AVG(adjusted_close)  OVER w50  AS ma_50,
    AVG(adjusted_close)  OVER w200 AS ma_200,
    MAX(adjusted_close)  OVER w52  AS high_52w,
    MIN(adjusted_close)  OVER w52  AS low_52w,
    STDDEV(log_return)   OVER w60  * SQRT(252) AS realized_vol_60d,
    REGR_SLOPE(log_return, bm_return) OVER w252 AS beta_spy_252d
FROM joined
WINDOW
    w20  AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN  19 PRECEDING AND CURRENT ROW),
    w50  AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN  49 PRECEDING AND CURRENT ROW),
    w200 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW),
    w52  AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW),
    w60  AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN  59 PRECEDING AND CURRENT ROW),
    w252 AS (PARTITION BY ticker ORDER BY date ROWS BETWEEN 251 PRECEDING AND CURRENT ROW)
"""


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(_build_sql(_benchmark_ticker()))
