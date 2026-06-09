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
async def test_full_pipeline_merge_dedup_and_concepts(news_collector):
    """End-to-end: multi-source merge → dedup → relevance scoring → concept extraction."""
    from src.portfolio.models import Holding
    await news_collector.portfolio.add_holding(
        Holding(symbol="300750", name="宁德时代", market="CN")
    )

    # Mock two sources with overlap
    news_collector._data_collector._sources["eastmoney"].get_news = AsyncMock(return_value=[
        {"title": "宁德时代固态电池量产", "content": "...", "source": "东方财富", "time": "2026-05-28 14:00:00", "url": ""},
        {"title": "锂电池板块走强", "content": "...", "source": "东方财富", "time": "2026-05-28 10:00:00", "url": ""},
    ])
    news_collector._data_collector._sources["sina"].get_news = AsyncMock(return_value=[
        {"title": "宁德时代固态电池量产", "content": "...", "source": "新浪", "time": "2026-05-28 13:00:00", "url": ""},  # dup
        {"title": "无人驾驶新规发布", "content": "...", "source": "新浪", "time": "2026-05-28 09:00:00", "url": ""},
    ])

    result = await news_collector.get_news("300750")

    # 3 unique articles after dedup
    assert len(result) == 3

    # Sorted by time desc
    assert result[0].title == "宁德时代固态电池量产"
    assert result[1].title == "锂电池板块走强"
    assert result[2].title == "无人驾驶新规发布"

    # Relevance: "宁德时代" matches name (0.4) + symbol not in title
    assert result[0].relevance_score >= 0.4

    # Concept extraction
    assert "固态电池" in result[0].concepts
    assert "无人驾驶" in result[2].concepts


@pytest.mark.asyncio
async def test_caching_preserves_concepts(news_collector):
    """Cached NewsItem should include concepts round-trip."""
    from src.portfolio.models import Holding
    await news_collector.portfolio.add_holding(
        Holding(symbol="000001", name="平安银行", market="CN")
    )

    news_collector._data_collector._sources["eastmoney"].get_news = AsyncMock(return_value=[
        {"title": "数据要素赋能银行转型", "content": "...", "source": "东方财富", "time": "2026-05-28", "url": ""},
    ])
    news_collector._data_collector._sources["sina"].get_news = AsyncMock(return_value=[])

    # First call — hits sources
    result1 = await news_collector.get_news("000001")
    assert "数据要素" in result1[0].concepts

    # Second call — should hit cache
    result2 = await news_collector.get_news("000001")
    assert "数据要素" in result2[0].concepts
