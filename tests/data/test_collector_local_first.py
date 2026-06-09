import pytest
from datetime import datetime
from unittest.mock import AsyncMock

from src.data.collector import DataCollector
from src.data.cache import DataCache
from src.data.historical_store import HistoricalDataStore


@pytest.fixture
async def collector_with_history(test_settings):
    test_settings.local_history_enabled = True
    cache = DataCache(test_settings)
    await cache.init_db()
    store = HistoricalDataStore(test_settings)
    await store.init_db()
    collector = DataCollector(test_settings, cache)
    collector._historical_store = store
    return collector


@pytest.mark.asyncio
async def test_collector_reads_local_kline_when_available(collector_with_history):
    collector = collector_with_history
    today = datetime.now().strftime("%Y-%m-%d")
    # Pre-populate local store with today's data so it's returned immediately
    records = [
        {"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000},
        {"date": today, "open": 10.5, "high": 11.2, "low": 10.3, "close": 11.0, "volume": 120000},
    ]
    await collector._historical_store.save_kline("603738", "1d", records)

    # Mock all API sources to ensure they are NOT called
    for name in ["sina", "eastmoney", "tencent", "baostock"]:
        if name in collector._sources:
            collector._sources[name].get_kline = AsyncMock(return_value=None)

    result = await collector.get_kline("603738", period="1d", limit=2)
    assert result is not None
    assert len(result) == 2

    # Verify no API source was called
    for name in ["sina", "eastmoney", "tencent", "baostock"]:
        if name in collector._sources:
            collector._sources[name].get_kline.assert_not_called()


@pytest.mark.asyncio
async def test_collector_refreshes_local_kline_when_history_too_short(collector_with_history):
    collector = collector_with_history
    today = datetime.now().strftime("%Y-%m-%d")
    await collector._historical_store.save_kline(
        "603738",
        "1d",
        [{"date": today, "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000}],
    )
    api_records = [
        {
            "date": f"2025-01-{day:02d}",
            "open": 10.0,
            "high": 11.0,
            "low": 9.5,
            "close": 10.5,
            "volume": 100000,
        }
        for day in range(1, 10)
    ] + [
        {"date": today, "open": 10.5, "high": 11.2, "low": 10.3, "close": 11.0, "volume": 120000}
    ]
    collector._sources["sina"].get_kline = AsyncMock(return_value=api_records)

    result = await collector.get_kline("603738", period="1d", limit=10)

    assert result is not None
    assert len(result) == 10
    collector._sources["sina"].get_kline.assert_called_once_with("603738", period="1d", limit=10)


@pytest.mark.asyncio
async def test_collector_falls_back_to_api_when_local_missing(collector_with_history):
    collector = collector_with_history
    # Local store is empty
    api_records = [
        {"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000},
    ]
    collector._sources["sina"].get_kline = AsyncMock(return_value=api_records)

    result = await collector.get_kline("603738", period="1d", limit=10)
    assert result is not None
    assert len(result) == 1
    collector._sources["sina"].get_kline.assert_called_once()

    # Verify data was saved to local store
    local = await collector._historical_store.load_kline("603738", "1d")
    assert local is not None
    assert len(local) == 1


@pytest.mark.asyncio
async def test_collector_disabled_local_history_uses_api_only(test_settings):
    test_settings.local_history_enabled = False
    cache = DataCache(test_settings)
    await cache.init_db()
    collector = DataCollector(test_settings, cache)

    api_records = [
        {"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000},
    ]
    collector._sources["sina"].get_kline = AsyncMock(return_value=api_records)

    result = await collector.get_kline("603738", period="1d", limit=10)
    assert result is not None
    assert len(result) == 1
    collector._sources["sina"].get_kline.assert_called_once()
