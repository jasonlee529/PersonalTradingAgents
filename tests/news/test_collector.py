import pytest
from unittest.mock import AsyncMock
from src.news.collector import NewsCollector


@pytest.fixture
async def news_collector(test_settings):
    from src.data.cache import DataCache
    from src.data.collector import DataCollector
    from src.portfolio.manager import PortfolioManager
    cache = DataCache(test_settings)
    await cache.init_db()
    portfolio = PortfolioManager(test_settings)
    await portfolio.init_db()
    dc = DataCollector(test_settings, cache)
    nc = NewsCollector(test_settings, cache, portfolio, data_collector=dc)
    return nc


@pytest.mark.asyncio
async def test_get_news_filters_by_relevance(news_collector):
    # Add holding so name can be resolved
    from src.portfolio.models import Holding
    await news_collector.portfolio.add_holding(
        Holding(symbol="600519", name="贵州茅台", market="CN")
    )
    # Mock DataCollector sources to avoid real network calls
    news_collector._data_collector._sources["eastmoney"].get_news = AsyncMock(return_value=[
        {"title": "600519贵州茅台年报", "content": "600519贵州茅台", "source": "东方财富", "time": "2026-05-26", "url": ""}
    ])
    news_collector._data_collector._sources["sina"].get_news = AsyncMock(return_value=[])
    result = await news_collector.get_news("600519")
    assert len(result) >= 1
    assert result[0].relevance_score > 0.5


@pytest.mark.asyncio
async def test_get_news_uses_data_collector_merge(news_collector):
    """NewsCollector should merge from multiple sources via DataCollector."""
    from src.portfolio.models import Holding
    await news_collector.portfolio.add_holding(
        Holding(symbol="600519", name="贵州茅台", market="CN")
    )
    # Mock DataCollector's two sources to return overlapping + unique articles
    news_collector._data_collector._sources["eastmoney"].get_news = AsyncMock(return_value=[
        {"title": "贵州茅台年报超预期", "content": "...", "source": "东方财富", "time": "2026-05-28 10:00:00", "url": ""},
        {"title": "白酒板块集体上涨", "content": "...", "source": "东方财富", "time": "2026-05-28 09:00:00", "url": ""},
    ])
    news_collector._data_collector._sources["sina"].get_news = AsyncMock(return_value=[
        {"title": "贵州茅台年报超预期", "content": "...", "source": "新浪", "time": "2026-05-28 10:05:00", "url": ""},  # dup
        {"title": "茅台新品发布", "content": "...", "source": "新浪", "time": "2026-05-28 08:00:00", "url": ""},
    ])

    result = await news_collector.get_news("600519", limit=10)
    # Should dedupe: 3 unique titles total
    titles = [r.title for r in result]
    assert len(titles) == 3
    assert "贵州茅台年报超预期" in titles
    assert "白酒板块集体上涨" in titles
    assert "茅台新品发布" in titles
    # Most recent first (sorted by time desc)
    assert titles[0] == "贵州茅台年报超预期"
