import duckdb
import pandas as pd

from ._util import to_date, to_float, upsert_df


def ingest_shares(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    quarterly = data.get("outstandingShares", {}).get("quarterly", {})
    rows = [
        {
            "ticker": ticker,
            "period_end": to_date(entry.get("dateFormatted")),
            "shares": entry.get("shares"),
            "shares_mln": to_float(entry.get("sharesMln")),
        }
        for entry in quarterly.values()
    ]
    if rows:
        upsert_df(con, "shares_outstanding", pd.DataFrame(rows), ["ticker", "period_end"])
