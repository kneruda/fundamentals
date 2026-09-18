"""HTTP contract tests for the FastAPI adapter."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client():
    from src.api.main import app, get_connection
    from src.ingest.orchestrator import ingest_ticker
    from src.schema.runner import open_db

    con = open_db(":memory:")
    ingest_ticker(con, FIXTURES / "AAPL-Fundamentals.json", FIXTURES / "AAPL.json")
    con.execute("INSERT INTO universe (ticker, added_at, active) VALUES ('AAPL', now(), true)")
    app.dependency_overrides[get_connection] = lambda: con
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    con.close()


def test_openapi_exposes_typed_dashboard_contract(client):
    schema = client.get("/openapi.json").json()

    assert "/api/v1/dashboard" in schema["paths"]
    assert "DashboardResponse" in schema["components"]["schemas"]


def test_company_endpoints_serialize_existing_query_results(client):
    overview = client.get("/api/v1/companies/AAPL/overview")
    valuation = client.get("/api/v1/companies/AAPL/valuation?years=5")
    prices = client.get("/api/v1/companies/AAPL/prices?limit=3")

    assert overview.status_code == 200
    assert valuation.status_code == 200
    assert "history" in valuation.json()
    assert prices.status_code == 200
    assert prices.json()["total"] >= len(prices.json()["rows"])


def test_screen_endpoint_uses_existing_screen_service(client):
    response = client.post(
        "/api/v1/screens/fundamental/absolute_valuation",
        json={"filters": {"min_fcf_yield": 1.0}},
    )

    assert response.status_code == 200
    assert response.json()["rows"][0]["ticker"] == "AAPL"


def test_watchlist_crud_contract(client):
    created = client.post(
        "/api/v1/watchlists",
        json={"name": "API list", "tickers": ["AAPL"], "description": "contract test"},
    )
    watchlist_id = created.json()["watchlist_id"]
    replaced = client.put(f"/api/v1/watchlists/{watchlist_id}", json={"tickers": ["AAPL"]})
    deleted = client.delete(f"/api/v1/watchlists/{watchlist_id}")

    assert created.status_code == 201
    assert replaced.status_code == 200
    assert deleted.status_code == 204
