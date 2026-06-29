import pytest
from unittest.mock import AsyncMock
from src.data.collector import DEFAULT_KLINE_LIMIT, DataCollector


@pytest.fixture
async def collector(test_settings):
    from src.data.cache import DataCache
    cache = DataCache(test_settings)
    await cache.init_db()
    c = DataCollector(test_settings, cache)
    return c


@pytest.mark.asyncio
async def test_collector_uses_cache(collector):
    # Pre-warm cache
    await collector.cache.set(
        "quote:CN:600519",
        {"symbol": "600519", "name": "贵州茅台", "price": 1500.0, "volume": 100, "turnover": 1000.0},
        ttl=300,
    )
    # Mock sources to ensure they are NOT called
    collector._sources["tencent"].get_quote = AsyncMock(return_value=None)
    collector._sources["eastmoney"].get_quote = AsyncMock(return_value=None)

    result = await collector.get_quote("600519")
    assert result["price"] == 1500.0
    collector._sources["tencent"].get_quote.assert_not_called()
    collector._sources["eastmoney"].get_quote.assert_not_called()


@pytest.mark.asyncio
async def test_collector_enriches_incomplete_quote_cache(collector):
    await collector.cache.set("quote:CN:600519", {"symbol": "600519", "price": 1500.0, "volume": 0}, ttl=300)
    collector._sources["tencent"].get_quote = AsyncMock(return_value=None)
    collector._sources["eastmoney"].get_quote = AsyncMock(return_value={
        "symbol": "600519",
        "name": "贵州茅台",
        "price": 1501.0,
        "volume": 1200,
        "turnover": 1800000.0,
        "source": "eastmoney",
    })

    result = await collector.get_quote("600519")

    assert result["price"] == 1500.0
    assert result["name"] == "贵州茅台"
    assert result["volume"] == 1200
    collector._sources["eastmoney"].get_quote.assert_called_once_with("600519")


@pytest.mark.asyncio
async def test_collector_fallback_to_source(collector):
    # Ensure cache miss; mock tencent to return None, eastmoney to succeed
    collector._sources["tencent"].get_quote = AsyncMock(return_value=None)
    collector._sources["eastmoney"].get_quote = AsyncMock(return_value={"price": 1500.0, "source": "eastmoney"})

    result = await collector.get_quote("600519")
    assert result["price"] == 1500.0
    collector._sources["tencent"].get_quote.assert_called_once_with("600519")
    collector._sources["eastmoney"].get_quote.assert_called_once_with("600519")


@pytest.mark.asyncio
async def test_collector_get_kline_defaults_to_two_year_limit(collector):
    collector._sources["sina"].get_kline = AsyncMock(return_value=[])

    await collector.get_kline("600519")

    collector._sources["sina"].get_kline.assert_called_once_with(
        "600519", period="1d", limit=DEFAULT_KLINE_LIMIT
    )


@pytest.mark.asyncio
async def test_collector_snapshot_uses_two_year_kline_limit(collector):
    collector.get_quote = AsyncMock(return_value=None)
    collector.get_kline = AsyncMock(return_value=[])
    collector.get_fundamentals = AsyncMock(return_value=None)
    collector.get_indicators = AsyncMock(return_value=None)

    await collector.get_full_snapshot("600519")

    collector.get_kline.assert_called_once_with("600519", limit=DEFAULT_KLINE_LIMIT)


@pytest.mark.asyncio
async def test_collector_no_us_special_case(collector):
    """US tickers no longer get yfinance hardcoding; they use default priority."""
    collector._sources["tencent"].get_quote = AsyncMock(return_value=None)
    collector._sources["eastmoney"].get_quote = AsyncMock(return_value=None)
    collector._sources["sina"].get_quote = AsyncMock(return_value=None)

    result = await collector.get_quote("AAPL")
    # A-share sources don't handle US tickers, so result is None
    assert result is None
    # Verify it tried the default priority sources, not yfinance
    collector._sources["tencent"].get_quote.assert_called_once_with("AAPL")
    collector._sources["eastmoney"].get_quote.assert_called_once_with("AAPL")


@pytest.mark.asyncio
async def test_collector_rejects_foreign_priority(collector):
    collector._priority["quote"] = ["yfinance"]

    with pytest.raises(RuntimeError, match="Unsupported or foreign data source"):
        await collector.get_quote("600519")


@pytest.mark.asyncio
async def test_collector_list_concept_boards(collector):
    collector._sources["eastmoney"].list_concept_boards = AsyncMock(return_value=[
        {"code": "BK1033", "name": "固态电池", "change_pct": 5.23, "source": "eastmoney"}
    ])
    result = await collector.list_concept_boards()
    assert len(result) == 1
    assert result[0]["code"] == "BK1033"


@pytest.mark.asyncio
async def test_collector_get_board_stocks(collector):
    collector._sources["eastmoney"].get_board_stocks = AsyncMock(return_value=[
        {"symbol": "300750", "name": "宁德时代", "price": 210.5, "change_pct": 3.25, "source": "eastmoney"}
    ])
    result = await collector.get_board_stocks("BK1033")
    assert len(result) == 1
    assert result[0]["symbol"] == "300750"


@pytest.mark.asyncio
async def test_collector_market_overview_defaults_to_eastmoney_when_priority_missing(collector):
    collector._priority.pop("market_indices", None)
    collector._priority.pop("market_statistics", None)
    collector._priority.pop("sector_rankings", None)
    collector._sources["eastmoney"].get_market_indices = AsyncMock(
        return_value=[{"name": "SSE Composite", "current": 3123.45, "change_pct": -0.12}]
    )
    collector._sources["eastmoney"].get_market_statistics = AsyncMock(
        return_value={"up_count": 1200, "down_count": 3800, "total_amount": 8200}
    )
    collector._sources["eastmoney"].get_sector_rankings = AsyncMock(return_value=([], []))

    indices = await collector.get_market_indices()
    stats = await collector.get_market_statistics()
    rankings = await collector.get_sector_rankings()

    assert indices[0]["name"] == "SSE Composite"
    assert stats["total_amount"] == 8200
    assert rankings == ([], [])
    collector._sources["eastmoney"].get_market_indices.assert_awaited_once_with()
    collector._sources["eastmoney"].get_market_statistics.assert_awaited_once_with()
    collector._sources["eastmoney"].get_sector_rankings.assert_awaited_once_with(n=5)


@pytest.mark.asyncio
async def test_collector_market_indices_fallbacks_to_tencent(collector):
    collector._priority["market_indices"] = ["eastmoney", "tencent", "sina"]
    collector._sources["eastmoney"].get_market_indices = AsyncMock(return_value=None)
    collector._sources["tencent"].get_market_indices = AsyncMock(
        return_value=[{"name": "SSE Composite", "current": 3123.45, "source": "tencent"}]
    )
    collector._sources["sina"].get_market_indices = AsyncMock(return_value=[])

    result = await collector.get_market_indices()

    assert result[0]["source"] == "tencent"
    collector._sources["eastmoney"].get_market_indices.assert_awaited_once_with()
    collector._sources["tencent"].get_market_indices.assert_awaited_once_with()
    collector._sources["sina"].get_market_indices.assert_not_called()


@pytest.mark.asyncio
async def test_collector_market_statistics_fallbacks_to_sina(collector):
    collector._priority["market_statistics"] = ["eastmoney", "sina"]
    collector._sources["eastmoney"].get_market_statistics = AsyncMock(return_value=None)
    collector._sources["sina"].get_market_statistics = AsyncMock(
        return_value={"up_count": 1200, "down_count": 3800, "source": "sina"}
    )

    result = await collector.get_market_statistics()

    assert result["source"] == "sina"
    collector._sources["eastmoney"].get_market_statistics.assert_awaited_once_with()
    collector._sources["sina"].get_market_statistics.assert_awaited_once_with()
