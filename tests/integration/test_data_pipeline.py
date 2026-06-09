import pytest
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector
from src.portfolio.manager import PortfolioManager
from src.news.collector import NewsCollector
from src.portfolio.models import Holding


@pytest.fixture
async def pipeline(test_settings):
    cache = DataCache(test_settings)
    await cache.init_db()
    portfolio = PortfolioManager(test_settings)
    await portfolio.init_db()
    collector = DataCollector(test_settings, cache)
    news = NewsCollector(test_settings, cache, portfolio)
    return {"cache": cache, "portfolio": portfolio, "collector": collector, "news": news}


@pytest.mark.asyncio
async def test_end_to_end_holdings_and_cache(pipeline):
    pm = pipeline["portfolio"]
    cache = pipeline["cache"]

    await pm.add_holding(Holding(symbol="600519", name="贵州茅台", market="CN"))
    holdings = await pm.list_holdings()
    assert len(holdings) == 1

    await cache.set("test", {"value": 1}, ttl=60)
    assert await cache.get("test") == {"value": 1}


@pytest.mark.asyncio
async def test_collector_cache_hit(pipeline):
    collector = pipeline["collector"]
    # Use a US ticker so detect_market returns "US" and cache key matches
    await collector.cache.set("quote:US:AAPL", {"price": 99.9}, ttl=300)

    result = await collector.get_quote("AAPL")
    assert result["price"] == 99.9
