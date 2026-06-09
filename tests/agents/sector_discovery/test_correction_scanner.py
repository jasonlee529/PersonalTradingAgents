import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.sector_discovery.scanners.correction_scanner import CorrectionScanner
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, test_mode=True)


@pytest.fixture
def scanner(settings):
    mock_cache = MagicMock()
    mock_collector = MagicMock()
    return CorrectionScanner(settings, mock_cache, mock_collector)


@pytest.mark.asyncio
async def test_correction_scanner_finds_pullback_stocks(scanner):
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "房地产", "change_pct": -6.0},
        {"code": "BK002", "name": "银行", "change_pct": 1.0},
    ])
    scanner.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "000001", "name": "平安银行", "change_pct": "-6.5"},
    ])
    scanner.collector.get_fundamentals = AsyncMock(return_value={
        "pe_ttm": 15.0, "pb": 1.5, "roe": 0.12,
        "revenue_growth": 0.25, "debt_ratio": 50.0,
    })
    scanner.collector.get_quote = AsyncMock(return_value={"change_pct": -6.5})

    result = await scanner.scan()

    assert len(result.stocks) >= 1
    assert result.stocks[0].dimension == "correction"
    assert "回调" in result.stocks[0].reason or "低吸" in result.stocks[0].reason


@pytest.mark.asyncio
async def test_correction_scanner_skips_shallow_pullback(scanner):
    """Boards with change_pct > -5 should be ignored."""
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "银行", "change_pct": -2.0},
    ])

    result = await scanner.scan()

    assert len(result.stocks) == 0
