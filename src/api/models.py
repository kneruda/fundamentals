"""Pydantic request and response models for the public HTTP API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnMeta(BaseModel):
    key: str
    label: str
    format: Literal["number", "percent", "currency", "date", "text"] = "text"


class TableResponse(BaseModel):
    columns: list[ColumnMeta]
    rows: list[dict[str, Any]]
    total: int | None = None
    excluded_count: int = 0


class HealthResponse(BaseModel):
    status: Literal["ok"]
    warehouse_updated_at: datetime | None = None


class DashboardResponse(TableResponse):
    warehouse_updated_at: datetime | None = None


class Watchlist(BaseModel):
    watchlist_id: int
    name: str
    description: str | None = None
    created_at: datetime | None = None
    member_count: int


class WatchlistDetail(Watchlist):
    tickers: list[str]


class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tickers: list[str] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=1000)


class WatchlistReplaceRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)


class WatchlistRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CompanyOverviewResponse(BaseModel):
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None
    price_date: str | None = None
    price: float | None = None
    pct_1d: float | None = None
    mktcap_b: float | None = None
    next_period_end: str | None = None


class CompanyValuationResponse(BaseModel):
    history: TableResponse
    statistics: TableResponse


class CompanyDividendsResponse(BaseModel):
    latest: dict[str, Any] | None = None
    annual_history: TableResponse


class CompanyTechnicalsResponse(BaseModel):
    series: TableResponse
    signals: dict[str, Any] | None = None


class ScreenRequest(BaseModel):
    watchlist_id: int | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class TickerCreateRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    notes: str | None = Field(default=None, max_length=1000)


class BulkTickerCreateRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)


class ActionResult(BaseModel):
    ticker: str | None = None
    message: str


class BulkActionResult(BaseModel):
    results: list[dict[str, Any]]
