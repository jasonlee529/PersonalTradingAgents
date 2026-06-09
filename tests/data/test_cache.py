# tests/data/test_cache.py
import pytest
import time
from src.data.cache import DataCache


@pytest.fixture
async def cache(test_settings):
    c = DataCache(test_settings)
    await c.init_db()
    return c


@pytest.mark.asyncio
async def test_set_and_get(cache):
    await cache.set("quote:600519", {"price": 1500.0}, ttl=3600)
    result = await cache.get("quote:600519")
    assert result == {"price": 1500.0}


@pytest.mark.asyncio
async def test_cache_miss(cache):
    result = await cache.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_ttl_expiry(cache):
    await cache.set("temp", "value", ttl=0)
    time.sleep(0.1)
    assert await cache.get("temp") is None
