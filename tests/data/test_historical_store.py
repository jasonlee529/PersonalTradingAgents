import pytest
from src.data.historical_store import HistoricalDataStore
from src.config import Settings


@pytest.fixture
async def store(temp_dir):
    settings = Settings(
        data_dir=temp_dir / "data",
        knowledge_dir=temp_dir / "data" / "knowledge",
        cache_db_path=temp_dir / "data" / "db" / "cache.db",
        portfolio_db_path=temp_dir / "data" / "db" / "portfolio.db",
        historical_db_path=temp_dir / "data" / "db" / "historical.db",
        runtime_cache_dir=temp_dir / "data" / "cache",
        analysis_artifacts_dir=temp_dir / "data" / "artifacts" / "analysis",
        checkpoint_dir=temp_dir / "data" / "db" / "checkpoints",
    )
    store = HistoricalDataStore(settings)
    await store.init_db()
    return store


@pytest.mark.asyncio
async def test_save_and_load_kline(store):
    records = [
        {"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000},
        {"date": "2025-01-03", "open": 10.5, "high": 11.2, "low": 10.3, "close": 11.0, "volume": 120000},
    ]
    await store.save_kline("603738", "1d", records)
    loaded = await store.load_kline("603738", "1d", start_date="2025-01-01", end_date="2025-01-31")
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0]["date"] == "2025-01-02"
    assert loaded[0]["close"] == 10.5


@pytest.mark.asyncio
async def test_load_kline_date_range_filter(store):
    records = [
        {"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000},
        {"date": "2025-01-03", "open": 10.5, "high": 11.2, "low": 10.3, "close": 11.0, "volume": 120000},
        {"date": "2025-01-06", "open": 11.0, "high": 11.5, "low": 10.8, "close": 11.2, "volume": 90000},
    ]
    await store.save_kline("603738", "1d", records)
    loaded = await store.load_kline("603738", "1d", start_date="2025-01-03", end_date="2025-01-05")
    assert len(loaded) == 1
    assert loaded[0]["date"] == "2025-01-03"


@pytest.mark.asyncio
async def test_upsert_overwrites_existing(store):
    await store.save_kline("603738", "1d", [{"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000}])
    await store.save_kline("603738", "1d", [{"date": "2025-01-02", "open": 20.0, "high": 21.0, "low": 19.5, "close": 20.5, "volume": 200000}])
    loaded = await store.load_kline("603738", "1d")
    assert len(loaded) == 1
    assert loaded[0]["close"] == 20.5


@pytest.mark.asyncio
async def test_get_date_range(store):
    records = [
        {"date": "2025-01-02", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100000},
        {"date": "2025-01-03", "open": 10.5, "high": 11.2, "low": 10.3, "close": 11.0, "volume": 120000},
    ]
    await store.save_kline("603738", "1d", records)
    min_date, max_date = await store.get_date_range("603738", "1d")
    assert min_date == "2025-01-02"
    assert max_date == "2025-01-03"
