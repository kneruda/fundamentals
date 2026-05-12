import duckdb
import pandas as pd

from ._util import to_date, to_float, upsert_df


def ingest_dividends(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    sd = data.get("SplitsDividends", {})
    currency = data.get("General", {}).get("CurrencyCode")

    ex_date = to_date(sd.get("ExDividendDate"))
    if ex_date:
        upsert_df(
            con,
            "dividends_declared",
            pd.DataFrame(
                [
                    {
                        "ticker": ticker,
                        "ex_date": ex_date,
                        "pay_date": to_date(sd.get("DividendDate")),
                        "forward_annual_dividend_rate": to_float(
                            sd.get("ForwardAnnualDividendRate")
                        ),
                        "forward_annual_dividend_yield": to_float(
                            sd.get("ForwardAnnualDividendYield")
                        ),
                        "payout_ratio": to_float(sd.get("PayoutRatio")),
                        "currency": currency,
                    }
                ]
            ),
            ["ticker", "ex_date"],
        )

    annual_rows = [
        {"ticker": ticker, "year": entry["Year"], "count": entry["Count"]}
        for entry in sd.get("NumberDividendsByYear", {}).values()
    ]
    if annual_rows:
        upsert_df(con, "dividends_annual", pd.DataFrame(annual_rows), ["ticker", "year"])

    split_date = to_date(sd.get("LastSplitDate"))
    factor = sd.get("LastSplitFactor")
    if split_date and factor:
        upsert_df(
            con,
            "splits",
            pd.DataFrame([{"ticker": ticker, "split_date": split_date, "factor": factor}]),
            ["ticker", "split_date"],
        )
