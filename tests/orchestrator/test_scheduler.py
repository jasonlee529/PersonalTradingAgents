# tests/orchestrator/test_scheduler.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.orchestrator.scheduler import (
    AnalysisScheduler,
    AnalysisHandler,
    DataRefreshHandler,
    SectorDiscoveryHandler,
)


@pytest.fixture
def mock_job_store():
    store = MagicMock()
    store.list_scheduled_tasks = AsyncMock(return_value=[])
    store.save_scheduled_task = AsyncMock()
    return store


@pytest.fixture
def scheduler(test_settings, mock_job_store):
    pipeline = MagicMock()
    pipeline.run_all = AsyncMock(return_value=[])
    return AnalysisScheduler(
        settings=test_settings,
        job_store=mock_job_store,
        pipeline=pipeline,
    )


def test_scheduler_not_started_by_default(scheduler):
    assert scheduler.is_running() is False


def test_scheduler_list_tasks_default(scheduler):
    tasks = scheduler.list_tasks()
    assert len(tasks) == 3
    ids = {t["id"] for t in tasks}
    assert ids == {"analysis", "data_refresh", "sector_discovery"}


@pytest.mark.asyncio
async def test_scheduler_load_tasks_seeds_defaults(scheduler, mock_job_store):
    mock_job_store.list_scheduled_tasks.return_value = []
    tasks = await scheduler.load_tasks()
    assert len(tasks) == 3
    # Should have seeded DB
    assert mock_job_store.save_scheduled_task.call_count == 3


@pytest.mark.asyncio
async def test_scheduler_load_tasks_from_db(scheduler, mock_job_store):
    mock_job_store.list_scheduled_tasks.return_value = [
        {"id": "analysis", "name": "AI 分析", "description": "", "enabled": True, "cron": "0 10 * * 1-5"},
        {"id": "data_refresh", "name": "持仓数据刷新", "description": "", "enabled": False, "cron": "0 6 * * 1-5"},
        {"id": "sector_discovery", "name": "今日方向", "description": "", "enabled": False, "cron": "0 8 * * 1-5"},
    ]
    tasks = await scheduler.load_tasks()
    analysis_task = next(t for t in tasks if t["id"] == "analysis")
    assert analysis_task["enabled"] is True
    assert analysis_task["cron"] == "0 10 * * 1-5"


@pytest.mark.asyncio
async def test_scheduler_start_stop(scheduler, mock_job_store):
    mock_job_store.list_scheduled_tasks.return_value = [
        {"id": "analysis", "name": "AI 分析", "description": "", "enabled": True, "cron": "0 9 * * 1-5"},
        {"id": "data_refresh", "name": "持仓数据刷新", "description": "", "enabled": False, "cron": "0 6 * * 1-5"},
        {"id": "sector_discovery", "name": "今日方向", "description": "", "enabled": False, "cron": "0 8 * * 1-5"},
    ]
    await scheduler.load_tasks()
    scheduler.start()
    assert scheduler.is_running() is True
    scheduler.stop()
    assert scheduler.is_running() is False


@pytest.mark.asyncio
async def test_update_task(scheduler, mock_job_store):
    await scheduler.load_tasks()
    await scheduler.update_task("analysis", enabled=True, cron="0 11 * * 1-5")
    task = next(t for t in scheduler.list_tasks() if t["id"] == "analysis")
    assert task["enabled"] is True
    assert task["cron"] == "0 11 * * 1-5"
    mock_job_store.save_scheduled_task.assert_called()


@pytest.mark.asyncio
async def test_run_task_now(scheduler):
    await scheduler.load_tasks()
    scheduler._tasks["sector_discovery"].handler_factory = lambda: SectorDiscoveryHandler()
    result = await scheduler.run_task_now("sector_discovery")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_run_task_now_unknown(scheduler):
    result = await scheduler.run_task_now("nonexistent")
    assert result["success"] is False


@pytest.mark.asyncio
async def test_analysis_handler_run():
    pipeline = MagicMock()
    pipeline.run_all = AsyncMock(return_value=[MagicMock()])
    handler = AnalysisHandler(pipeline=pipeline)
    result = await handler.run()
    assert result["success"] is True
    pipeline.run_all.assert_called_once()


@pytest.mark.asyncio
async def test_data_refresh_handler_no_collector():
    handler = DataRefreshHandler()
    result = await handler.run()
    assert result["success"] is False


@pytest.mark.asyncio
async def test_sector_discovery_handler_run():
    handler = SectorDiscoveryHandler()
    result = await handler.run()
    assert result["success"] is True
    assert "stub" in result["message"].lower() or "not yet" in result["message"]
