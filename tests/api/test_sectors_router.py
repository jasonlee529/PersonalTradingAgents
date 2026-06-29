import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api.routers.sectors import _is_valid_direction_analysis
from src.config import Settings
from src.utils.trading_dates import normalize_trade_date


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        knowledge_dir=tmp_path / "knowledge",
    )
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


# ── GET /api/sectors/today ────────────────────────────────────────────────

def test_get_today_directions_empty(client):
    response = client.get("/api/sectors/today")
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == normalize_trade_date()
    assert data["reports"] == []


def test_get_today_directions_with_date(client):
    response = client.get("/api/sectors/today?date=2026-05-30")
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-05-30"


def test_get_today_directions_defaults_to_latest_available(client):
    asyncio.run(client.app.state.services.raw_store.add_source(
        source_kind="daily_direction",
        origin="agent",
        title="2026-06-15 今日方向",
        markdown="# 2026-06-15 今日方向\n\nAI 算力",
        metadata={
            "trade_date": "2026-06-15",
            "summary": "AI 算力",
            "analysis_data": {
                "market_overview": {
                    "statistics": {
                        "up_count": 1500,
                        "down_count": 800,
                        "flat_count": 100,
                    },
                },
                "selected_directions": [{"name": "AI 算力", "rank": 1}],
            },
            "run_id": "test-latest-daily-direction",
        },
    ))

    response = client.get("/api/sectors/today")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-06-15"
    assert data["reports"][0]["date"] == "2026-06-15"
    assert data["reports"][0]["sectors"] == [{"name": "AI 算力", "rank": 1}]


def test_get_today_directions_keeps_legacy_reports_as_history(client):
    asyncio.run(client.app.state.services.raw_store.add_source(
        source_kind="daily_direction",
        origin="agent",
        title="2026-06-15 今日方向",
        markdown="# 2026-06-15 今日方向\n\nAI 算力",
        metadata={
            "trade_date": "2026-06-15",
            "summary": "AI 算力",
            "analysis_data": {
                "market_overview": {
                    "statistics": {
                        "up_count": 1500,
                        "down_count": 800,
                        "flat_count": 100,
                    },
                },
                "selected_directions": [{"name": "AI 算力", "rank": 1}],
            },
            "run_id": "test-valid-daily-direction",
        },
    ))
    asyncio.run(client.app.state.services.raw_store.add_source(
        source_kind="daily_direction",
        origin="agent",
        title="2026-06-12 今日方向",
        markdown="# 2026-06-12 今日方向\n\n半导体",
        metadata={
            "trade_date": "2026-06-12",
            "summary": "半导体",
            "analysis_data": {
                "selected_directions": [{"name": "半导体", "rank": 1}],
            },
            "run_id": "test-legacy-daily-direction",
        },
    ))

    response = client.get("/api/sectors/today")

    assert response.status_code == 200
    data = response.json()
    assert [report["date"] for report in data["reports"]] == ["2026-06-15", "2026-06-12"]
    assert data["reports"][1]["sectors"] == [{"name": "半导体", "rank": 1}]


def test_invalid_direction_analysis_rejects_one_page_market_stats():
    assert not _is_valid_direction_analysis({
        "market_overview": {
            "statistics": {
                "up_count": 77,
                "down_count": 22,
                "flat_count": 1,
                "limit_up_count": 1,
                "total_amount": 72.25,
            }
        }
    })


def test_invalid_direction_analysis_rejects_missing_market_stats():
    assert not _is_valid_direction_analysis({
        "market_overview": {},
        "candidate_directions": [
            {"name": "AI算力", "raw_metrics": {"limit_up_count": 16}},
        ],
    })


# ── POST /api/sectors/discover ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_sector_discovery(client):
    with patch("src.api.routers.sectors.Coordinator") as MockCoordinator, \
         patch("src.api.routers.sectors.DataCollector") as MockCollector:

        mock_report = MagicMock()
        mock_report.date = "2026-05-30"
        mock_report.summary = "测试报告"
        mock_report.sectors = []

        mock_coordinator = AsyncMock()
        mock_coordinator.run = AsyncMock(return_value=mock_report)
        MockCoordinator.return_value = mock_coordinator

        mock_collector = MagicMock()
        MockCollector.return_value = mock_collector

        response = client.post("/api/sectors/discover")
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

        # Check status endpoint
        job_id = data["job_id"]
        status_resp = client.get(f"/api/sectors/discover/status/{job_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["job_id"] == job_id
        assert status_data["status"] in ("pending", "running", "completed")


# ── POST /api/sectors/{stock}/analyze ─────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_stock(client):
    with patch("src.agents.trading_agents_wrapper.TradingAgentsWrapper") as MockWrapper:

        mock_wrapper = AsyncMock()
        mock_wrapper.analyze = AsyncMock(return_value={"decision": "Buy"})
        MockWrapper.return_value = mock_wrapper

        response = client.post("/api/sectors/600519/analyze")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "600519"
        assert data["status"] == "completed"


def test_run_sector_discovery_rejects_llm_provider(client):
    response = client.post(
        "/api/sectors/discover",
        json={"llm_provider": "deepseek"},
    )

    assert response.status_code == 422
