import duckdb
import pandas as pd

from ._util import col, to_date, to_float, upsert_df

_BASE_FIELDS = {"date", "filing_date", "currency_symbol"}


def _parse_quarterly(ticker: str, quarterly: dict, currency_default: str) -> list[dict]:
    rows = []
    for _, entry in quarterly.items():
        row: dict = {
            "ticker": ticker,
            "fiscal_period_end": to_date(entry.get("date")),
            "report_date": to_date(entry.get("filing_date")),
            "currency": entry.get("currency_symbol") or currency_default,
        }
        for k, v in entry.items():
            if k not in _BASE_FIELDS:
                row[col(k)] = to_float(v)
        rows.append(row)
    return rows


def ingest_financials(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    fin = data.get("Financials", {})
    currency = data.get("General", {}).get("CurrencyCode", "USD")
    pk = ["ticker", "fiscal_period_end"]

    for section_key, table in [
        ("Balance_Sheet", "balance_sheet"),
        ("Income_Statement", "income_statement"),
        ("Cash_Flow", "cash_flow"),
    ]:
        quarterly = fin.get(section_key, {}).get("quarterly", {})
        if quarterly:
            rows = _parse_quarterly(ticker, quarterly, currency)
            upsert_df(con, table, pd.DataFrame(rows), pk)
