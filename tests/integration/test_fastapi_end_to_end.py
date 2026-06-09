import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def e2e_client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_health(e2e_client):
    resp = e2e_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_add_holding_and_fetch_data(e2e_client):
    # Add holding
    resp = e2e_client.post("/api/portfolio/holdings", json={
        "symbol": "TEST001", "name": "测试股", "market": "CN",
        "quantity": 100, "avg_cost": 10.0,
    })
    assert resp.status_code == 200

    # List holdings
    resp = e2e_client.get("/api/portfolio/holdings")
    assert resp.status_code == 200
    holdings = resp.json()
    assert len(holdings) == 1
    assert holdings[0]["holding"]["symbol"] == "TEST001"

    # Get quote (may be empty for fake symbol)
    resp = e2e_client.get("/api/stocks/TEST001/quote")
    assert resp.status_code == 200

    # Remove holding
    resp = e2e_client.delete("/api/portfolio/holdings/TEST001")
    assert resp.status_code == 200

    resp = e2e_client.get("/api/portfolio/holdings")
    assert resp.json() == []
