import pytest
from unittest.mock import patch, MagicMock

from src.data.sources.eastmoney_source import EastmoneySource
from src.data.sources.sina_source import SinaSource
from src.data.sources.tencent_source import TencentSource
from src.data.sources.baostock_source import BaoStockSource
from src.data.collector import DataCollector
from src.data.cache import DataCache

TARGET = "603738"
live = pytest.mark.live


# ---------------------------------------------------------------------------
# Task 1: EastmoneySource.get_kline — mock test (push2his may be unreachable
# in some network environments; we verify parsing logic with mocked response)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eastmoney_get_kline_parsing():
    """Verify Eastmoney kline parsing with mocked response."""
    source = EastmoneySource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "klines": [
                "2025-01-02,10.5,11.0,11.2,10.3,150000,1650000.0,8.57,4.76,0.50,2.35",
                "2025-01-03,11.0,10.8,11.1,10.7,120000,1296000.0,3.64,-1.82,-0.20,1.88",
            ]
        }
    }

    with patch(
        "src.data.sources.eastmoney_source.requests.get",
        return_value=mock_resp,
    ):
        result = await source.get_kline(TARGET, period="1d", limit=5)

    assert result is not None
    assert len(result) == 2
    first = result[0]
    assert first["date"] == "2025-01-02"
    assert first["open"] == 10.5
    assert first["close"] == 11.0
    assert first["high"] == 11.2
    assert first["low"] == 10.3
    assert first["volume"] == 150000
    assert first["turnover"] == 1650000.0
    assert first["amplitude"] == 8.57
    assert first["change_pct"] == 4.76
    assert first["change_amt"] == 0.50
    assert first["turnover_rate"] == 2.35


@pytest.mark.asyncio
async def test_eastmoney_get_kline_empty_response():
    """Verify Eastmoney kline returns None on empty klines."""
    source = EastmoneySource()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"klines": []}}

    with patch(
        "src.data.sources.eastmoney_source.requests.get",
        return_value=mock_resp,
    ):
        result = await source.get_kline(TARGET, period="1d", limit=5)

    assert result is None


# ---------------------------------------------------------------------------
# Task 3: E2E integration tests (live network)
# ---------------------------------------------------------------------------

@pytest.fixture
async def real_collector(test_settings):
    cache = DataCache(test_settings)
    await cache.init_db()
    return DataCollector(test_settings, cache)


@pytest.mark.asyncio
@live
async def test_sina_kline_603738():
    source = SinaSource()
    data = await source.get_kline(TARGET, period="1d", limit=5)
    assert data is not None and len(data) > 0
    assert all(f in data[0] for f in ["date", "open", "high", "low", "close", "volume"])


@pytest.mark.asyncio
@live
async def test_tencent_quote_603738():
    source = TencentSource()
    data = await source.get_quote(TARGET)
    assert data is not None
    assert data["symbol"] == TARGET
    assert "price" in data


@pytest.mark.asyncio
@live
async def test_baostock_kline_603738():
    source = BaoStockSource()
    data = await source.get_kline(TARGET, period="1d", limit=5)
    assert data is not None and len(data) > 0
    assert all(f in data[0] for f in ["date", "open", "high", "low", "close", "volume"])


@pytest.mark.asyncio
@live
async def test_collector_fallback_kline_603738(real_collector):
    """E2E: Collector should fetch 603738 kline through fallback chain."""
    kline = await real_collector.get_kline(TARGET, period="1d", limit=5)
    assert kline is not None and len(kline) > 0
    assert all(f in kline[0] for f in ["date", "open", "high", "low", "close", "volume"])


@pytest.mark.asyncio
@live
async def test_collector_fallback_quote_603738(real_collector):
    """E2E: Collector should fetch 603738 quote through fallback chain."""
    quote = await real_collector.get_quote(TARGET)
    assert quote is not None
    assert quote.get("symbol") == TARGET
    assert "price" in quote
