import pytest
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_get_quote_not_found(client):
    resp = client.get("/api/stocks/UNKNOWN/quote")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "UNKNOWN"
    assert data["price"] == 0


def test_get_kline_empty(client):
    resp = client.get("/api/stocks/UNKNOWN/kline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "UNKNOWN"
    assert data["data"] == []
