import pytest
from unittest.mock import patch, MagicMock
from src.data.sources.yfinance_source import YFinanceSource


@pytest.fixture
async def source(test_settings):
    return YFinanceSource(test_settings)


@pytest.mark.asyncio
async def test_get_quote_mocked(source):
    mock_ticker = MagicMock()
    mock_info = {
        "currentPrice": 180.0,
        "open": 178.0,
        "dayHigh": 181.0,
        "dayLow": 177.5,
        "previousClose": 177.0,
        "volume": 50000000,
        "regularMarketChangePercent": 1.69,
    }
    mock_ticker.info = mock_info

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = await source.get_quote("AAPL")
        assert result is not None
        assert result["price"] == 180.0
        assert result["source"] == "yfinance"


@pytest.mark.asyncio
async def test_get_quote_no_info_returns_none(source):
    mock_ticker = MagicMock()
    mock_ticker.info = None

    with patch("yfinance.Ticker", return_value=mock_ticker):
        result = await source.get_quote("FAKE")
        assert result is None
