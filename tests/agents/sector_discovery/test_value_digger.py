import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.sector_discovery.scanners.value_digger import ValueDigger
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def scanner(settings):
    mock_cache = MagicMock()
    mock_collector = MagicMock()
    return ValueDigger(settings, mock_cache, mock_collector)


# ── Board-level scan ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_value_digger_empty_when_no_boards(scanner):
    scanner.collector.list_industry_boards = AsyncMock(return_value=None)
    scanner.collector.list_concept_boards = AsyncMock(return_value=None)

    result = await scanner.scan()

    assert result.dimension == "value"
    assert result.stocks == []


@pytest.mark.asyncio
async def test_value_digger_finds_moderate_boards(scanner):
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "银行", "change_pct": 1.5, "turnover": 5e9},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    result = await scanner.scan()

    assert len(result.stocks) == 1
    assert result.stocks[0].symbol == "BK001"
    assert result.stocks[0].name == "银行"
    assert result.stocks[0].dimension == "value"
    assert result.stocks[0].score > 5.0


@pytest.mark.asyncio
async def test_value_digger_skips_surged_boards(scanner):
    """Boards that surged > 20% should be excluded."""
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "过热板块", "change_pct": 25.0, "turnover": 5e9},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    result = await scanner.scan()
    assert result.stocks == []


@pytest.mark.asyncio
async def test_value_digger_skips_crashed_boards(scanner):
    """Boards that crashed < -15% should be excluded."""
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "暴跌板块", "change_pct": -20.0, "turnover": 5e9},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    result = await scanner.scan()
    assert result.stocks == []


@pytest.mark.asyncio
async def test_value_digger_prefers_flat_boards(scanner):
    """Very flat boards (|change| < 2%) get higher scores."""
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "银行", "change_pct": 0.5, "turnover": 5e9},
        {"code": "BK002", "name": "半导体", "change_pct": 12.0, "turnover": 5e9},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    result = await scanner.scan()

    assert len(result.stocks) == 2
    assert result.stocks[0].symbol == "BK001"  # flat board scores higher
    assert result.stocks[0].score > result.stocks[1].score


@pytest.mark.asyncio
async def test_value_digger_merges_industry_and_concept(scanner):
    """Should merge industry and concept boards, deduplicate by code."""
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "银行", "change_pct": 1.0, "turnover": 3e9},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "银行", "change_pct": 1.0, "turnover": 3e9},  # dup
        {"code": "BK003", "name": "固态电池", "change_pct": 2.0, "turnover": 8e9},
    ])

    result = await scanner.scan()

    symbols = {s.symbol for s in result.stocks}
    assert symbols == {"BK001", "BK003"}


@pytest.mark.asyncio
async def test_value_digger_reason_building(scanner):
    scanner.collector.list_industry_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "银行", "change_pct": 0.5, "turnover": 5e9},
    ])
    scanner.collector.list_concept_boards = AsyncMock(return_value=[])

    result = await scanner.scan()

    reason = result.stocks[0].reason
    assert "板块涨幅" in reason
    assert "波动极小" in reason


@pytest.mark.asyncio
async def test_value_digger_single_board_code(scanner):
    """When board_code is provided, return pseudo-board for that code."""
    scanner.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "600519", "name": "茅台"},
    ])

    result = await scanner.scan(board_code="BK001")

    assert len(result.stocks) == 1
    assert result.stocks[0].symbol == "BK001"
