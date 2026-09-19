"""HTTP-facing application services; no FastAPI or Streamlit imports."""

from datetime import datetime
from typing import Any

import duckdb
import pandas as pd

from src import universe
from src.compute.technicals import recompute_technicals
from src.ingest.fetch import fetch_news
from src.services import queries, universe_jobs
from src.services.screeners import (
    run_forward_screen,
    run_fundamental_screen,
    run_technical_screen,
)
from src.services.watchlists import available_watchlists, display_filter_for_watchlist
from src.watchlist import (
    create_watchlist,
    delete_watchlist,
    get_membership,
    rename_watchlist,
    replace_membership,
)


class UpstreamDataUnavailableError(RuntimeError):
    """Raised when an optional vendor-backed dashboard surface is unavailable."""


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, dict):
        return value
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def table(df: pd.DataFrame, *, total: int | None = None, excluded_count: int = 0) -> dict[str, Any]:
    """Serialize a dataframe without presentation formatting."""
    rows = [
        {key: _json_value(value) for key, value in row.items()} for row in df.to_dict("records")
    ]
    return {
        "columns": [{"key": key, "label": key.replace("_", " ").title()} for key in df.columns],
        "rows": rows,
        "total": total if total is not None else len(rows),
        "excluded_count": excluded_count,
    }


def dashboard(con: duckdb.DuckDBPyConnection, watchlist_id: int | None) -> dict[str, Any]:
    df = queries.universe_summary(con)
    display_filter = display_filter_for_watchlist(con, watchlist_id)
    if display_filter is not None:
        df = df[df["ticker"].isin(display_filter)].reset_index(drop=True)
    result = table(df)
    result["warehouse_updated_at"] = warehouse_updated_at()
    return result


def warehouse_updated_at() -> datetime | None:
    mtime = queries.warehouse_mtime()
    return datetime.fromtimestamp(mtime) if mtime else None


def company_overview(con: duckdb.DuckDBPyConnection, ticker: str) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in queries.ticker_header(con, ticker).items()}


def company_valuation(con: duckdb.DuckDBPyConnection, ticker: str, years: int) -> dict[str, Any]:
    history = queries.valuation_history(con, ticker, years)
    return {"history": table(history), "statistics": table(queries.valuation_stats(history))}


def company_dividends(con: duckdb.DuckDBPyConnection, ticker: str, years: int) -> dict[str, Any]:
    latest = queries.latest_dividends(con, ticker)
    if latest is not None:
        latest = {key: _json_value(value) for key, value in latest.items()}
    return {
        "latest": latest,
        "annual_history": table(queries.dividend_annual_history(con, ticker).head(years)),
    }


def company_technicals(
    con: duckdb.DuckDBPyConnection, ticker: str, lookback_days: int | None
) -> dict[str, Any]:
    df = queries.deep_dive_technicals(con, ticker, lookback_days)
    signals: dict[str, Any] | None = None
    if not df.empty:
        latest = df.iloc[-1]
        signals = {
            key: _json_value(latest[key])
            for key in [
                "rsi_14",
                "macd_histogram",
                "pct_from_sma_200",
                "pct_from_52w_high",
                "volume_ratio",
            ]
        }
    return {"series": table(df), "signals": signals}


def company_table(
    con: duckdb.DuckDBPyConnection, resource: str, ticker: str, **params: Any
) -> dict[str, Any]:
    functions = {
        "profitability": lambda: queries.quarterly_metrics(con, ticker, params.get("periods", 12)),
        "analyst": lambda: pd.DataFrame([queries.latest_analyst_snapshot(con, ticker)]).dropna(
            how="all"
        ),
        "earnings": lambda: queries.earnings_history(con, ticker).head(params.get("limit", 16)),
        "statement": lambda: queries.statement(
            con,
            ticker,
            params["statement_type"],
            params.get("period_type", "quarterly"),
            params.get("depth", "summary"),
            params.get("limit", 8),
        ),
    }
    return table(functions[resource]())


def company_prices(con: duckdb.DuckDBPyConnection, ticker: str, **params: Any) -> dict[str, Any]:
    df = queries.prices_page(con, ticker, **params)
    total = queries.prices_count(
        con, ticker, date_from=params.get("date_from"), date_to=params.get("date_to")
    )
    return table(df, total=total)


def company_news(ticker: str, limit: int = 50) -> dict[str, Any]:
    """Return the existing vendor news payload in the standard table contract.

    News is the sole Deep Dive surface backed by the vendor rather than the
    warehouse.  Keeping that call here preserves a Streamlit-free HTTP layer
    and lets the UI use the same typed table response as every other surface.
    """
    try:
        return table(pd.DataFrame(fetch_news(ticker, limit=limit)))
    except (OSError, RuntimeError, ValueError) as exc:
        raise UpstreamDataUnavailableError(
            "Recent news is currently unavailable from the market-data provider."
        ) from exc


def screen(
    con: duckdb.DuckDBPyConnection,
    family: str,
    name: str,
    watchlist_id: int | None,
    filters: dict[str, Any],
) -> dict[str, Any]:
    display_filter = display_filter_for_watchlist(con, watchlist_id)
    runners = {
        "fundamental": run_fundamental_screen,
        "forward": run_forward_screen,
        "technical": run_technical_screen,
    }
    try:
        result = runners[family](con, name, display_filter=display_filter, filters=filters)
    except KeyError as exc:
        raise ValueError(f"Unsupported screen family: {family}") from exc
    return table(result.rows, excluded_count=result.excluded_count)


def sectors(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    return table(queries.sector_summary(con))


def sector_constituents(
    con: duckdb.DuckDBPyConnection, sector: str, watchlist_id: int | None
) -> dict[str, Any]:
    return table(
        queries.sector_constituents(
            con, sector, display_filter=display_filter_for_watchlist(con, watchlist_id)
        )
    )


def watchlists(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in available_watchlists(con).to_dict("records")
    ]


def watchlist_detail(con: duckdb.DuckDBPyConnection, watchlist_id: int) -> dict[str, Any]:
    rows = available_watchlists(con)
    row = rows[rows["watchlist_id"] == watchlist_id]
    if row.empty:
        raise ValueError(f"Watchlist not found: {watchlist_id}")
    result = {key: _json_value(value) for key, value in row.iloc[0].to_dict().items()}
    result["tickers"] = get_membership(con, watchlist_id)
    return result


def create_list(
    con: duckdb.DuckDBPyConnection, name: str, tickers: list[str], description: str | None
) -> dict[str, Any]:
    return watchlist_detail(con, create_watchlist(con, name, tickers, description))


def create_list_input(
    con: duckdb.DuckDBPyConnection,
    name: str,
    tickers: list[str],
    text: str | None,
    description: str | None,
) -> dict[str, Any]:
    """Create a list with the shared newline-oriented ticker parser."""
    parsed = (
        universe.parse_tickers(text) if text else [ticker.strip().upper() for ticker in tickers]
    )
    if not parsed:
        raise ValueError("Provide at least one ticker.")
    return create_list(con, name, parsed, description)


def replace_list(
    con: duckdb.DuckDBPyConnection, watchlist_id: int, tickers: list[str]
) -> dict[str, Any]:
    replace_membership(con, watchlist_id, tickers)
    return watchlist_detail(con, watchlist_id)


def replace_list_input(
    con: duckdb.DuckDBPyConnection,
    watchlist_id: int,
    tickers: list[str],
    text: str | None,
) -> dict[str, Any]:
    """Replace list members with the same parser used by Universe input."""
    parsed = (
        universe.parse_tickers(text) if text else [ticker.strip().upper() for ticker in tickers]
    )
    if not parsed:
        raise ValueError("Provide at least one ticker.")
    return replace_list(con, watchlist_id, parsed)


def rename_list(con: duckdb.DuckDBPyConnection, watchlist_id: int, name: str) -> dict[str, Any]:
    current = watchlist_detail(con, watchlist_id)
    rename_watchlist(con, current["name"], name)
    return watchlist_detail(con, watchlist_id)


def remove_list(con: duckdb.DuckDBPyConnection, watchlist_id: int) -> None:
    delete_watchlist(con, watchlist_id)


def add_ticker(con: duckdb.DuckDBPyConnection, ticker: str, notes: str | None) -> dict[str, str]:
    universe.add_ticker(con, ticker.upper(), notes)
    return {"ticker": ticker.upper(), "message": "Ticker added"}


def bulk_add_tickers(con: duckdb.DuckDBPyConnection, tickers: list[str]) -> list[dict[str, Any]]:
    return [
        {"ticker": ticker, "ok": ok, "message": message}
        for ticker, ok, message in universe.bulk_add_tickers(con, tickers)
    ]


def bulk_add_ticker_input(
    con: duckdb.DuckDBPyConnection, tickers: list[str], text: str | None
) -> list[dict[str, Any]]:
    """Use the shared ticker parser for pasted or uploaded universe input."""
    parsed = (
        universe.parse_tickers(text) if text else [ticker.strip().upper() for ticker in tickers]
    )
    if not parsed:
        raise ValueError("Provide at least one ticker.")
    return bulk_add_tickers(con, parsed)


def universe_fundamentals(
    con: duckdb.DuckDBPyConnection, ticker: str, period_type: str
) -> dict[str, Any]:
    n_periods = 8 if period_type == "quarterly" else 5
    return {
        statement_type: table(
            queries.fundamentals_recent(con, ticker, statement_type, period_type, n_periods)
        )
        for statement_type in ("income_statement", "balance_sheet", "cash_flow")
    }


def start_universe_refresh() -> dict[str, Any]:
    return universe_jobs.start_refresh_all()


def universe_refresh_job(job_id: str) -> dict[str, Any]:
    return universe_jobs.get_refresh_job(job_id)


def remove_ticker(con: duckdb.DuckDBPyConnection, ticker: str) -> None:
    universe.remove_ticker(con, ticker.upper())


def recompute(con: duckdb.DuckDBPyConnection) -> None:
    recompute_technicals(con)
