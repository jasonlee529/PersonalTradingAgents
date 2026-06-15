from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app


@pytest.fixture
async def collector(test_settings):
    from src.data.cache import DataCache
    from src.data.collector import DataCollector

    cache = DataCache(test_settings)
    await cache.init_db()
    return DataCollector(test_settings, cache)


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    app.state.auth_tokens.add("test-token")
    with TestClient(app) as test_client:
        yield test_client


def _headers():
    return {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_collector_filters_mainboard_limit_up_stocks(collector):
    collector._sources["eastmoney"].get_limit_up_stocks = AsyncMock(return_value=[
        {"symbol": "600001", "name": "沪主板", "trade_date": "2026-06-15"},
        {"symbol": "000001", "name": "深主板", "trade_date": "2026-06-15"},
        {"symbol": "300001", "name": "创业板", "trade_date": "2026-06-15"},
        {"symbol": "688001", "name": "科创板", "trade_date": "2026-06-15"},
        {"symbol": "920001", "name": "北交所", "trade_date": "2026-06-15"},
    ])

    result = await collector.get_limit_up_stocks("2026-06-15")

    assert [item["symbol"] for item in result] == ["600001", "000001"]
    assert [item["market"] for item in result] == ["sh", "sz"]


@pytest.mark.asyncio
async def test_collector_filters_limit_up_stocks_by_market(collector):
    collector._sources["eastmoney"].get_limit_up_stocks = AsyncMock(return_value=[
        {"symbol": "600001", "name": "沪主板", "trade_date": "2026-06-15"},
        {"symbol": "000001", "name": "深主板", "trade_date": "2026-06-15"},
    ])

    result = await collector.get_limit_up_stocks("2026-06-15", market="sh")

    assert [item["symbol"] for item in result] == ["600001"]


def test_limit_up_endpoint_filters_by_keyword(client):
    client.app.state.services.collector.get_limit_up_stocks = AsyncMock(return_value=[
        {
            "symbol": "600001",
            "name": "沪主板A",
            "market": "sh",
            "trade_date": "2026-06-15",
            "price": 10.0,
            "change_pct": 10.0,
            "volume": 1000,
            "turnover": 100000.0,
        },
        {
            "symbol": "000001",
            "name": "深主板B",
            "market": "sz",
            "trade_date": "2026-06-15",
            "price": 12.0,
            "change_pct": 10.0,
        },
    ])

    response = client.get(
        "/api/stocks/limit-up?trade_date=2026-06-15&q=沪主板",
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["symbol"] == "600001"


def test_limit_up_endpoint_returns_empty_result(client):
    client.app.state.services.collector.get_limit_up_stocks = AsyncMock(return_value=[])

    response = client.get("/api/stocks/limit-up?trade_date=2026-06-15", headers=_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_limit_up_endpoint_handles_collector_failure(client):
    client.app.state.services.collector.get_limit_up_stocks = AsyncMock(return_value=None)

    response = client.get("/api/stocks/limit-up?trade_date=2026-06-15", headers=_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
