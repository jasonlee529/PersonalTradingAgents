import pytest
from unittest.mock import AsyncMock

from src.agents.sector_discovery.scanners.market_heat import MarketHeatScanner


@pytest.fixture
async def hot_scanner(test_settings):
    from src.data.cache import DataCache
    cache = DataCache(test_settings)
    await cache.init_db()
    scanner = MarketHeatScanner(test_settings, cache)
    return scanner


@pytest.mark.asyncio
async def test_market_heat_scan_returns_hot_signals(hot_scanner):
    hot_scanner.collector.fetch_market_heatmap = AsyncMock(return_value=[
        {"code": "300750", "name": "宁德时代", "reason": "固态电池概念"},
        {"code": "002594", "name": "比亚迪", "reason": "新能源车"},
    ])
    hot_scanner.collector.fetch_order_flow_profile = AsyncMock(return_value={"net_inflow": 5e8})

    result = await hot_scanner.scan(trade_date="2026-06-05")
    assert isinstance(result, list)
    assert len(result) >= 1
    # Should extract concepts from reasons
    concepts = [h.concept for h in result]
    assert "固态电池" in concepts or "新能源车" in concepts
    assert all(h.heat_level > 0 for h in result)
    hot_scanner.collector.fetch_market_heatmap.assert_awaited_once_with(date="2026-06-05")


@pytest.mark.asyncio
async def test_market_heat_order_flow_profile_boosts_heat(hot_scanner):
    hot_scanner.collector.fetch_market_heatmap = AsyncMock(return_value=[
        {"code": "000001", "name": "平安银行", "reason": "银行板块"},
        {"code": "000002", "name": "万科A", "reason": "银行板块"},
        {"code": "000003", "name": "深发展", "reason": "银行板块"},
        {"code": "000004", "name": "国农科技", "reason": "银行板块"},
        {"code": "000005", "name": "世纪星源", "reason": "银行板块"},
    ])
    hot_scanner.collector.fetch_order_flow_profile = AsyncMock(return_value={"net_inflow": 2e8})

    result = await hot_scanner.scan()
    assert len(result) == 1
    # 5 stocks * 1.2 = 6.0 + 2.0 fund = 8.0, capped at 10
    assert result[0].heat_level >= 5.0


@pytest.mark.asyncio
async def test_market_heat_empty_on_failure(hot_scanner):
    hot_scanner.collector.fetch_market_heatmap = AsyncMock(side_effect=Exception("API down"))

    result = await hot_scanner.scan()
    assert result == []


@pytest.mark.asyncio
async def test_market_heat_extracts_concepts(hot_scanner):
    hot_scanner.collector.fetch_market_heatmap = AsyncMock(return_value=[
        {"code": "300001", "name": "特锐德", "reason": "固态电池+充电桩概念"},
        {"code": "300002", "name": "神州泰岳", "reason": "AI大模型应用落地"},
    ])
    hot_scanner.collector.fetch_order_flow_profile = AsyncMock(return_value=None)

    result = await hot_scanner.scan()
    concepts = {h.concept for h in result}
    assert "固态电池" in concepts or "AI算力" in concepts


