import duckdb
import pandas as pd

from ._util import to_date, to_float, upsert_df


def ingest_earnings(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    history = data.get("Earnings", {}).get("History", {})
    rows = [
        {
            "ticker": ticker,
            "fiscal_period_end": to_date(entry.get("date")),
            "report_date": to_date(entry.get("reportDate")),
            "before_after_market": entry.get("beforeAfterMarket"),
            "currency": entry.get("currency"),
            "eps_estimate": to_float(entry.get("epsEstimate")),
            "eps_actual": to_float(entry.get("epsActual")),
            "eps_difference": to_float(entry.get("epsDifference")),
            "surprise_percent": to_float(entry.get("surprisePercent")),
        }
        for entry in history.values()
    ]
    if rows:
        upsert_df(con, "earnings_events", pd.DataFrame(rows), ["ticker", "fiscal_period_end"])
