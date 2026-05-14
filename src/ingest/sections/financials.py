import duckdb
import pandas as pd

from ._util import col, to_date, to_float, upsert_df

_BASE_FIELDS = {"date", "filing_date", "currency_symbol"}


def _parse_periods(
    ticker: str, periods: dict, currency_default: str, period_type: str
) -> list[dict]:
    rows = []
    for _, entry in periods.items():
        if not isinstance(entry, dict):
            continue  # EODHD returns "NA" for fiscal years that don't align to calendar year
        row: dict = {
            "ticker": ticker,
            "fiscal_period_end": to_date(entry.get("date")),
            "report_date": to_date(entry.get("filing_date")),
            "currency": entry.get("currency_symbol") or currency_default,
            "period_type": period_type,
        }
        for k, v in entry.items():
            if k not in _BASE_FIELDS:
                row[col(k)] = to_float(v)
        rows.append(row)
    return rows


def ingest_financials(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    fin = data.get("Financials", {})
    currency = data.get("General", {}).get("CurrencyCode", "USD")
    pk = ["ticker", "fiscal_period_end", "period_type"]

    for section_key, table in [
        ("Balance_Sheet", "balance_sheet"),
        ("Income_Statement", "income_statement"),
        ("Cash_Flow", "cash_flow"),
    ]:
        section = fin.get(section_key, {})
        rows: list[dict] = []

        quarterly = section.get("quarterly", {})
        if quarterly:
            rows.extend(_parse_periods(ticker, quarterly, currency, "quarterly"))

        yearly = section.get("yearly", {})
        if yearly:
            rows.extend(_parse_periods(ticker, yearly, currency, "annual"))

        if rows:
            upsert_df(con, table, pd.DataFrame(rows), pk)
