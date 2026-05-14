import duckdb
import pandas as pd

from ._util import to_date, to_float, to_int, upsert_df


def ingest_general(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    g = data.get("General", {})
    row = {
        "ticker": ticker,
        "code": g.get("Code"),
        "exchange": g.get("Exchange"),
        "name": g.get("Name"),
        "type": g.get("Type"),
        "currency_code": g.get("CurrencyCode"),
        "country_name": g.get("CountryName"),
        "country_iso": g.get("CountryISO"),
        "isin": g.get("ISIN"),
        "cusip": g.get("CUSIP"),
        "cik": g.get("CIK"),
        "open_figi": g.get("OpenFigi"),
        "lei": g.get("LEI"),
        "primary_ticker": g.get("PrimaryTicker"),
        "sector": g.get("Sector"),
        "industry": g.get("Industry"),
        "gic_sector": g.get("GicSector"),
        "gic_group": g.get("GicGroup"),
        "gic_industry": g.get("GicIndustry"),
        "gic_sub_industry": g.get("GicSubIndustry"),
        "home_category": g.get("HomeCategory"),
        "fiscal_year_end": g.get("FiscalYearEnd"),
        "ipo_date": to_date(g.get("IPODate")),
        "is_delisted": bool(g.get("IsDelisted", False)),
        "full_time_employees": to_int(g.get("FullTimeEmployees")),
        "description": g.get("Description"),
        "web_url": g.get("WebURL"),
        "logo_url": g.get("LogoURL"),
        "vendor_updated_at": to_date(g.get("UpdatedAt")),
    }
    upsert_df(con, "security_master", pd.DataFrame([row]), ["ticker"])


def ingest_highlights(con: duckdb.DuckDBPyConnection, ticker: str, data: dict) -> None:
    h = data.get("Highlights", {})
    mrq = to_date(h.get("MostRecentQuarter"))
    if not mrq:
        return

    currency = data.get("General", {}).get("CurrencyCode")
    if not currency:
        raise ValueError(f"missing General.CurrencyCode for ticker={ticker!r}")

    row = {
        "ticker": ticker,
        "mrq_period_end": mrq,
        "currency": currency,
        "revenue_ttm": to_float(h.get("RevenueTTM")),
        "revenue_per_share_ttm": to_float(h.get("RevenuePerShareTTM")),
        "gross_profit_ttm": to_float(h.get("GrossProfitTTM")),
        "ebitda": to_float(h.get("EBITDA")),
        "profit_margin": to_float(h.get("ProfitMargin")),
        "operating_margin_ttm": to_float(h.get("OperatingMarginTTM")),
        "return_on_assets_ttm": to_float(h.get("ReturnOnAssetsTTM")),
        "return_on_equity_ttm": to_float(h.get("ReturnOnEquityTTM")),
        "diluted_eps_ttm": to_float(h.get("DilutedEpsTTM")),
        "earnings_share": to_float(h.get("EarningsShare")),
        "book_value": to_float(h.get("BookValue")),
        "dividend_share": to_float(h.get("DividendShare")),
        "quarterly_revenue_growth_yoy": to_float(h.get("QuarterlyRevenueGrowthYOY")),
        "quarterly_earnings_growth_yoy": to_float(h.get("QuarterlyEarningsGrowthYOY")),
    }
    upsert_df(con, "quarterly_fundamentals", pd.DataFrame([row]), ["ticker", "mrq_period_end"])
