import sys
from pathlib import Path

# Ensure src/agents/ is on sys.path for tradingagents imports
_agents_dir = Path(__file__).resolve().parent.parent.parent / "src" / "agents"
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

import pytest
from tradingagents.dataflows.interface import (
    route_to_vendor,
    VENDOR_METHODS,
    _is_a_share,
)


def test_is_a_share():
    assert _is_a_share("600519.SH") is True
    assert _is_a_share("000001.SZ") is True
    assert _is_a_share("300001") is True
    assert _is_a_share("AAPL") is False
    assert _is_a_share("TSLA") is False


def test_route_uses_data_for_a_share():
    """A-share tickers route to DataCollector-backed data vendor."""
    calls = []

    def mock_data_impl(*args):
        calls.append("data")
        return "from_data"

    VENDOR_METHODS.setdefault("get_stock_data", {})
    VENDOR_METHODS["get_stock_data"]["data"] = mock_data_impl

    try:
        result = route_to_vendor("get_stock_data", "600519.SH", "2024-01-01", "2024-01-31")
        assert result == "from_data"
        assert calls == ["data"]
    finally:
        if "data" in VENDOR_METHODS["get_stock_data"]:
            del VENDOR_METHODS["get_stock_data"]["data"]


def test_route_uses_data_for_non_a_share_ticker():
    """Non-A-share tickers still route to DataCollector, not foreign vendors."""
    calls = []

    def mock_data_impl(*args):
        calls.append("data")
        return "from_data"

    VENDOR_METHODS.setdefault("get_stock_data", {})
    VENDOR_METHODS["get_stock_data"]["data"] = mock_data_impl

    try:
        result = route_to_vendor("get_stock_data", "AAPL", "2024-01-01", "2024-01-31")
        assert result == "from_data"
        assert calls == ["data"]
    finally:
        if "data" in VENDOR_METHODS["get_stock_data"]:
            del VENDOR_METHODS["get_stock_data"]["data"]


def test_route_does_not_fallback_when_data_fails():
    """If data vendor raises, propagate the error without foreign fallback."""
    calls = []

    def mock_data_impl(*args):
        calls.append("data")
        raise RuntimeError("data unavailable")

    VENDOR_METHODS.setdefault("get_stock_data", {})
    VENDOR_METHODS["get_stock_data"]["data"] = mock_data_impl

    try:
        with pytest.raises(RuntimeError, match="data unavailable"):
            route_to_vendor("get_stock_data", "600519.SH", "2024-01-01", "2024-01-31")
        assert calls == ["data"]
    finally:
        if "data" in VENDOR_METHODS["get_stock_data"]:
            del VENDOR_METHODS["get_stock_data"]["data"]


def test_route_rejects_foreign_vendor_config(monkeypatch):
    """Foreign vendors in config fail fast."""
    from tradingagents.dataflows import interface

    monkeypatch.setattr(
        interface,
        "get_config",
        lambda: {"data_vendors": {"core_stock_apis": "yfinance"}},
    )

    with pytest.raises(RuntimeError, match="Only 'data' is allowed"):
        route_to_vendor("get_stock_data", "600519.SH", "2024-01-01", "2024-01-31")
