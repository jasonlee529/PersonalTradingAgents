# tests/utils/test_ticker.py
import pytest
from src.utils.ticker import detect_market, normalize_ticker


def test_detect_cn_market():
    assert detect_market("600519") == "CN"
    assert detect_market("000001") == "CN"
    assert detect_market("300750") == "CN"


def test_detect_us_market():
    assert detect_market("AAPL") == "US"
    assert detect_market("TSLA") == "US"


def test_normalize_strips_suffix():
    assert normalize_ticker("600519.SH") == "600519"
    assert normalize_ticker("000001.SZ") == "000001"


def test_normalize_preserves_us():
    assert normalize_ticker("AAPL") == "AAPL"
    assert normalize_ticker("BRK.B") == "BRK-B"
