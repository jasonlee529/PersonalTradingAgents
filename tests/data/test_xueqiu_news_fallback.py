from unittest.mock import AsyncMock

import pytest

from src.data.collector import DataCollector


@pytest.fixture
async def collector(test_settings):
    from src.data.cache import DataCache

    cache = DataCache(test_settings)
    await cache.init_db()
    return DataCollector(test_settings, cache)


@pytest.mark.asyncio
async def test_news_priority_tries_xueqiu_before_existing_sources(collector):
    assert collector._priority["news"][:3] == ["xueqiu", "eastmoney", "sina"]

    collector._sources["xueqiu"].get_news = AsyncMock(return_value=None)
    collector._sources["eastmoney"].get_news = AsyncMock(
        return_value=[
            {
                "title": "eastmoney news",
                "content": "",
                "source": "eastmoney",
                "time": "2026-06-01 10:00:00",
                "url": "",
            }
        ]
    )
    collector._sources["sina"].get_news = AsyncMock(
        return_value=[
            {
                "title": "sina news",
                "content": "",
                "source": "sina",
                "time": "2026-06-01 09:00:00",
                "url": "",
            }
        ]
    )

    result = await collector.get_news("600519", limit=10)

    assert [item["title"] for item in result] == ["eastmoney news", "sina news"]
    collector._sources["xueqiu"].get_news.assert_called_once()
    collector._sources["eastmoney"].get_news.assert_called_once()
    collector._sources["sina"].get_news.assert_called_once()
