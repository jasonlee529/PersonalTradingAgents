import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_list_holdings_empty(client):
    resp = client.get("/api/portfolio/holdings")
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_and_list_holding(client):
    resp = client.post("/api/portfolio/holdings", json={
        "symbol": "600519", "name": "贵州茅台", "market": "CN",
        "quantity": 100, "avg_cost": 1500.0,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "600519"

    resp = client.get("/api/portfolio/holdings")
    assert resp.status_code == 200
    holdings = resp.json()
    assert len(holdings) == 1
    assert holdings[0]["holding"]["symbol"] == "600519"


def test_position_edits_do_not_generate_daily_trade_log(client):
    resp = client.post("/api/portfolio/holdings", json={
        "symbol": "600519", "name": "贵州茅台", "market": "CN",
        "quantity": 100, "avg_cost": 1500.0,
    })
    assert resp.status_code == 200

    resp = client.patch("/api/portfolio/holdings/600519/position", json={
        "quantity": 120,
        "avg_cost": 1490.0,
        "current_price": 1510.0,
    })
    assert resp.status_code == 200

    raw_resp = client.get("/api/raw/sources", params={"source_kind": "daily_trade_log"})
    assert raw_resp.status_code == 200
    assert raw_resp.json() == []

    trades_resp = client.get("/api/portfolio/trades")
    assert trades_resp.status_code == 200
    assert trades_resp.json() == []


def test_list_holdings_does_not_resolve_names_from_quote(client):
    client.post("/api/portfolio/holdings", json={
        "symbol": "600519", "name": "贵州茅台", "market": "CN",
    })
    client.app.state.services.collector.get_quote = AsyncMock(side_effect=AssertionError(
        "list holdings should not fetch quotes"
    ))

    resp = client.get("/api/portfolio/holdings")

    assert resp.status_code == 200
    assert resp.json()[0]["holding"]["name"] == "贵州茅台"


def test_remove_holding(client):
    client.post("/api/portfolio/holdings", json={"symbol": "TEST", "market": "CN"})
    resp = client.delete("/api/portfolio/holdings/TEST")
    assert resp.status_code == 200
    resp = client.get("/api/portfolio/holdings")
    assert resp.json() == []


def test_refresh_prices(client):
    client.post("/api/portfolio/holdings", json={"symbol": "TEST", "market": "CN"})
    resp = client.post("/api/portfolio/refresh-prices")
    assert resp.status_code == 200
    assert resp.json()["status"] == "prices refreshed"
