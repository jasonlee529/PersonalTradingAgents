import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.sector_discovery.scanners.market_breadth_scanner import MarketBreadthScanner
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, test_mode=True)


@pytest.fixture
def scanner(settings):
    mock_cache = MagicMock()
    mock_collector = MagicMock()
    return MarketBreadthScanner(settings, mock_cache, mock_collector)


@pytest.mark.asyncio
async def test_market_breadth_scanner_detects_overheated(scanner):
    scanner.collector.get_market_statistics = AsyncMock(return_value={
        "up_count": 3500, "down_count": 1000,
    })
    scanner.collector.fetch_market_heatmap = AsyncMock(return_value=[
        {"code": "000001"} for _ in range(120)
    ])

    result = await scanner.scan()

    assert result.sentiment == "overheated"
    assert result.limit_up_count == 120


@pytest.mark.asyncio
async def test_market_breadth_scanner_detects_panic(scanner):
    scanner.collector.get_market_statistics = AsyncMock(return_value={
        "up_count": 500, "down_count": 4500,
    })
    scanner.collector.fetch_market_heatmap = AsyncMock(return_value=[])

    result = await scanner.scan()

    assert result.sentiment == "panic"

