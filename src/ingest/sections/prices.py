from datetime import UTC, datetime

import duckdb
import pandas as pd


def ingest_prices(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    records = data.get("_prices", [])
    if not records:
        return

    df = pd.DataFrame(records)
    df["ticker"] = ticker
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["loaded_at"] = datetime.now(UTC).replace(tzinfo=None)
    df = df[
        ["ticker", "date", "open", "high", "low", "close", "adjusted_close", "volume", "loaded_at"]
    ]

    tmp = "_stage_prices"
    con.register(tmp, df)
    try:
        con.execute(f"""
            INSERT INTO prices_daily
                (ticker, date, open, high, low, close, adjusted_close, volume, loaded_at)
            SELECT ticker, date, open, high, low, close, adjusted_close, volume, loaded_at
            FROM {tmp}
            ON CONFLICT (ticker, date) DO UPDATE SET
                open           = excluded.open,
                high           = excluded.high,
                low            = excluded.low,
                close          = excluded.close,
                adjusted_close = excluded.adjusted_close,
                volume         = excluded.volume,
                loaded_at      = excluded.loaded_at
        """)
    finally:
        con.unregister(tmp)
