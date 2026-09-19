"""FastAPI application. Route handlers intentionally delegate to services only."""

# ruff: noqa: B008

from collections.abc import Generator
from datetime import date
from pathlib import Path
from typing import Literal

import duckdb
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from src.api import models
from src.services import http_api, queries

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

app = FastAPI(title="Fundamentals Dashboard API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    con = queries.open_warehouse()
    try:
        yield con
    finally:
        con.close()


def _bad_request(exc: ValueError) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.get("/health", response_model=models.HealthResponse)
def health() -> dict:
    return {"status": "ok", "warehouse_updated_at": http_api.warehouse_updated_at()}


@app.get("/api/v1/dashboard", response_model=models.DashboardResponse)
def get_dashboard(watchlist_id: int | None = None, con=Depends(get_connection)) -> dict:
    return http_api.dashboard(con, watchlist_id)


@app.get("/api/v1/companies", response_model=models.TableResponse)
def get_companies(active: bool = True, con=Depends(get_connection)) -> dict:
    df = queries.universe_management_list(con)
    if active:
        df = df[df["active"]]
    return http_api.table(df[["ticker", "name", "sector", "active"]])


@app.get("/api/v1/companies/{ticker}/overview", response_model=models.CompanyOverviewResponse)
def get_company_overview(ticker: str, con=Depends(get_connection)) -> dict:
    result = http_api.company_overview(con, ticker.upper())
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not found")
    return result


@app.get("/api/v1/companies/{ticker}/valuation", response_model=models.CompanyValuationResponse)
def get_company_valuation(ticker: str, years: int = 5, con=Depends(get_connection)) -> dict:
    return http_api.company_valuation(con, ticker.upper(), years)


@app.get("/api/v1/companies/{ticker}/profitability", response_model=models.TableResponse)
def get_company_profitability(ticker: str, periods: int = 12, con=Depends(get_connection)) -> dict:
    return http_api.company_table(con, "profitability", ticker.upper(), periods=periods)


@app.get("/api/v1/companies/{ticker}/analyst", response_model=models.TableResponse)
def get_company_analyst(ticker: str, con=Depends(get_connection)) -> dict:
    return http_api.company_table(con, "analyst", ticker.upper())


@app.get("/api/v1/companies/{ticker}/earnings", response_model=models.TableResponse)
def get_company_earnings(ticker: str, limit: int = 16, con=Depends(get_connection)) -> dict:
    return http_api.company_table(con, "earnings", ticker.upper(), limit=limit)


@app.get("/api/v1/companies/{ticker}/dividends", response_model=models.CompanyDividendsResponse)
def get_company_dividends(ticker: str, years: int = 10, con=Depends(get_connection)) -> dict:
    return http_api.company_dividends(con, ticker.upper(), years)


@app.get(
    "/api/v1/companies/{ticker}/statements/{statement_type}", response_model=models.TableResponse
)
def get_company_statement(
    ticker: str,
    statement_type: Literal["income_statement", "balance_sheet", "cash_flow"],
    period_type: Literal["quarterly", "annual"] = "quarterly",
    depth: Literal["summary", "full"] = "summary",
    limit: int = 8,
    con=Depends(get_connection),
) -> dict:
    return http_api.company_table(
        con,
        "statement",
        ticker.upper(),
        statement_type=statement_type,
        period_type=period_type,
        depth=depth,
        limit=limit,
    )


@app.get("/api/v1/companies/{ticker}/technicals", response_model=models.CompanyTechnicalsResponse)
def get_company_technicals(
    ticker: str, lookback_days: int | None = 365, con=Depends(get_connection)
) -> dict:
    return http_api.company_technicals(con, ticker.upper(), lookback_days)


@app.get("/api/v1/companies/{ticker}/prices", response_model=models.TableResponse)
def get_company_prices(
    ticker: str,
    limit: int = 100,
    offset: int = 0,
    date_from: date | None = None,
    date_to: date | None = None,
    con=Depends(get_connection),
) -> dict:
    return http_api.company_prices(
        con,
        ticker.upper(),
        page_size=limit,
        offset=offset,
        date_from=str(date_from) if date_from else None,
        date_to=str(date_to) if date_to else None,
    )


@app.get("/api/v1/companies/{ticker}/news", response_model=models.TableResponse)
def get_company_news(ticker: str, limit: int = 50) -> dict:
    try:
        return http_api.company_news(ticker.upper(), limit)
    except http_api.UpstreamDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@app.get("/api/v1/universe", response_model=models.TableResponse)
def get_universe(active: bool | None = None, con=Depends(get_connection)) -> dict:
    df = queries.universe_management_list(con)
    if active is not None:
        df = df[df["active"] == active]
    return http_api.table(df)


@app.get("/api/v1/universe/snapshot-coverage", response_model=models.TableResponse)
def get_snapshot_coverage(con=Depends(get_connection)) -> dict:
    return http_api.table(queries.snapshot_coverage(con))


@app.get("/api/v1/sectors", response_model=models.TableResponse)
def get_sectors(con=Depends(get_connection)) -> dict:
    return http_api.sectors(con)


@app.get("/api/v1/sectors/{sector}/constituents", response_model=models.TableResponse)
def get_sector_constituents(
    sector: str, watchlist_id: int | None = None, con=Depends(get_connection)
) -> dict:
    return http_api.sector_constituents(con, sector, watchlist_id)


@app.post("/api/v1/universe/tickers", response_model=models.ActionResult)
def post_ticker(request: models.TickerCreateRequest, con=Depends(get_connection)) -> dict:
    return http_api.add_ticker(con, request.ticker, request.notes)


@app.post("/api/v1/universe/tickers/bulk", response_model=models.BulkActionResult)
def post_bulk_tickers(request: models.BulkTickerCreateRequest, con=Depends(get_connection)) -> dict:
    try:
        return {"results": http_api.bulk_add_ticker_input(con, request.tickers, request.text)}
    except ValueError as exc:
        _bad_request(exc)


@app.delete("/api/v1/universe/tickers/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticker(ticker: str, con=Depends(get_connection)) -> Response:
    http_api.remove_ticker(con, ticker)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/universe/tickers/{ticker}/refresh", response_model=models.ActionResult)
def post_refresh_ticker(ticker: str, con=Depends(get_connection)) -> dict:
    return http_api.add_ticker(con, ticker, None)


@app.post("/api/v1/universe/refresh", response_model=models.RefreshJobResponse)
def post_refresh_universe() -> dict:
    try:
        return http_api.start_universe_refresh()
    except ValueError as exc:
        _bad_request(exc)


@app.get("/api/v1/universe/refresh/{job_id}", response_model=models.RefreshJobResponse)
def get_refresh_universe(job_id: str) -> dict:
    try:
        return http_api.universe_refresh_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get(
    "/api/v1/universe/tickers/{ticker}/fundamentals",
    response_model=models.UniverseFundamentalsResponse,
)
def get_universe_ticker_fundamentals(
    ticker: str,
    period_type: Literal["quarterly", "annual"] = "quarterly",
    con=Depends(get_connection),
) -> dict:
    return http_api.universe_fundamentals(con, ticker.upper(), period_type)


@app.post("/api/v1/technicals/recompute", status_code=status.HTTP_204_NO_CONTENT)
def post_recompute_technicals(con=Depends(get_connection)) -> Response:
    http_api.recompute(con)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/watchlists", response_model=list[models.Watchlist])
def get_watchlists(con=Depends(get_connection)) -> list[dict]:
    return http_api.watchlists(con)


@app.post(
    "/api/v1/watchlists", response_model=models.WatchlistDetail, status_code=status.HTTP_201_CREATED
)
def post_watchlist(request: models.WatchlistCreateRequest, con=Depends(get_connection)) -> dict:
    try:
        return http_api.create_list_input(
            con, request.name, request.tickers, request.text, request.description
        )
    except ValueError as exc:
        _bad_request(exc)


@app.get("/api/v1/watchlists/{watchlist_id}", response_model=models.WatchlistDetail)
def get_watchlist(watchlist_id: int, con=Depends(get_connection)) -> dict:
    try:
        return http_api.watchlist_detail(con, watchlist_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.put("/api/v1/watchlists/{watchlist_id}", response_model=models.WatchlistDetail)
def put_watchlist(
    watchlist_id: int, request: models.WatchlistReplaceRequest, con=Depends(get_connection)
) -> dict:
    try:
        return http_api.replace_list_input(con, watchlist_id, request.tickers, request.text)
    except ValueError as exc:
        _bad_request(exc)


@app.patch("/api/v1/watchlists/{watchlist_id}", response_model=models.WatchlistDetail)
def patch_watchlist(
    watchlist_id: int, request: models.WatchlistRenameRequest, con=Depends(get_connection)
) -> dict:
    try:
        return http_api.rename_list(con, watchlist_id, request.name)
    except ValueError as exc:
        _bad_request(exc)


@app.delete("/api/v1/watchlists/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(watchlist_id: int, con=Depends(get_connection)) -> Response:
    http_api.remove_list(con, watchlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/screens/{family}/{screen_name}", response_model=models.TableResponse)
def post_screen(
    family: Literal["fundamental", "forward", "technical"],
    screen_name: str,
    request: models.ScreenRequest,
    con=Depends(get_connection),
) -> dict:
    try:
        return http_api.screen(con, family, screen_name, request.watchlist_id, request.filters)
    except ValueError as exc:
        _bad_request(exc)
