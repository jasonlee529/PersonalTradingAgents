import pytest
import pandas as pd
from src.data.sources.indicator_source import IndicatorSource


@pytest.fixture
def source(test_settings):
    return IndicatorSource(test_settings)


def test_compute_macd(source):
    # Fake OHLCV data
    df = pd.DataFrame({
        "open": [100, 101, 102, 101, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130],
        "high": [101, 102, 103, 102, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131],
        "low": [99, 100, 101, 100, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129],
        "close": [100.5, 101.5, 102.5, 101.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5, 111.5, 112.5, 113.5, 114.5, 115.5, 116.5, 117.5, 118.5, 119.5, 120.5, 121.5, 122.5, 123.5, 124.5, 125.5, 126.5, 127.5, 128.5, 129.5, 130.5],
        "volume": [1000] * 32,
    })
    result = source.compute(df, indicators=["macd"])
    assert "macd" in result
    assert "macd_signal" in result
    assert "macd_hist" in result


def test_compute_empty_returns_empty(source):
    df = pd.DataFrame()
    result = source.compute(df)
    assert result == {}


def test_compute_too_few_rows(source):
    df = pd.DataFrame({
        "open": [100, 101],
        "high": [101, 102],
        "low": [99, 100],
        "close": [100.5, 101.5],
        "volume": [1000, 1000],
    })
    result = source.compute(df)
    assert result == {}
