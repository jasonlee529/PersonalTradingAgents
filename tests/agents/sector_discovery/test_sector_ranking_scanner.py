import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.sector_discovery.scanners.sector_ranking_scanner import SectorRankingScanner
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, test_mode=True)


@pytest.fixture
def scanner(settings):
    mock_cache = MagicMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock(return_value=None)
    mock_collector = MagicMock()
    return SectorRankingScanner(settings, mock_cache, mock_collector)


@pytest.mark.asyncio
async def test_sector_ranking_scanner_detects_sudden_up(scanner):
    # Simulate a previous ranking where BK001 was at rank 15 (low)
    # and now it's at rank 0 (high) due to 5.0% change
    scanner.cache.get = AsyncMock(return_value='{"BK001": 15, "BK002": 1}')
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "半导体", "change_pct": 5.0},
        {"code": "BK002", "name": "银行", "change_pct": 0.5},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    result = await scanner.scan()

    assert len(result) >= 1
    trends = {r.trend for r in result}
    assert "sudden_up" in trends or "rising" in trends


@pytest.mark.asyncio
async def test_sector_ranking_scanner_caches_ranking(scanner):
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "半导体", "change_pct": 3.0},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    await scanner.scan()

    # Should cache current ranking for next comparison
    assert scanner.cache.set.called
