import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.data_collection import DataCollectionService
from src.portfolio.models import DataStatus


@pytest.mark.asyncio
async def test_collect_success():
    collector = MagicMock()
    collector.get_full_snapshot = AsyncMock(return_value={"quote": {"price": 100}})
    portfolio = MagicMock()
    portfolio.update_data_status = AsyncMock()

    svc = DataCollectionService(collector, portfolio)
    await svc.collect_for_symbol("TEST")

    assert portfolio.update_data_status.call_count == 2
    portfolio.update_data_status.assert_any_call("TEST", DataStatus.COLLECTING)
    portfolio.update_data_status.assert_called_with("TEST", DataStatus.READY)


@pytest.mark.asyncio
async def test_collect_empty():
    collector = MagicMock()
    collector.get_full_snapshot = AsyncMock(return_value={})
    portfolio = MagicMock()
    portfolio.update_data_status = AsyncMock()

    svc = DataCollectionService(collector, portfolio)
    await svc.collect_for_symbol("TEST")

    portfolio.update_data_status.assert_called_with("TEST", DataStatus.ERROR)


@pytest.mark.asyncio
async def test_collect_exception():
    collector = MagicMock()
    collector.get_full_snapshot = AsyncMock(side_effect=RuntimeError("API error"))
    portfolio = MagicMock()
    portfolio.update_data_status = AsyncMock()

    svc = DataCollectionService(collector, portfolio)
    await svc.collect_for_symbol("TEST")

    portfolio.update_data_status.assert_called_with("TEST", DataStatus.ERROR)


def test_start_collection_returns_task():
    collector = MagicMock()
    portfolio = MagicMock()
    svc = DataCollectionService(collector, portfolio)

    with patch("asyncio.create_task") as mock_create:
        mock_task = MagicMock()
        mock_create.return_value = mock_task
        result = svc.start_collection("TEST")
        assert result == mock_task
        mock_create.assert_called_once()
        mock_create.call_args.args[0].close()
