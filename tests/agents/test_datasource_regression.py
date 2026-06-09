"""Regression test: all analysis data flows through DataCollector."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure src/agents/ is on sys.path for tradingagents imports
_agents_dir = Path(__file__).resolve().parent.parent.parent / "src" / "agents"
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

from tradingagents.dataflows.interface import VENDOR_METHODS, route_to_vendor


@pytest.fixture(autouse=True)
def clean_vendor_methods():
    """Remove test-registered vendors from VENDOR_METHODS before/after each test."""
    for method_map in VENDOR_METHODS.values():
        method_map.pop("data", None)
        method_map.pop("yfinance", None)
        method_map.pop("alpha_vantage", None)
    yield
    for method_map in VENDOR_METHODS.values():
        method_map.pop("data", None)
        method_map.pop("yfinance", None)
        method_map.pop("alpha_vantage", None)


def test_a_share_routes_to_data_collector():
    """DataBridge registers data vendor and route_to_vendor calls it."""
    from src.agents.data_bridge import DataBridge

    mock_kline = [
        {
            "date": "2024-01-01",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10000,
        },
    ]
    mock_collector = MagicMock()
    mock_collector.get_kline = AsyncMock(return_value=mock_kline)

    bridge = DataBridge(MagicMock())
    bridge.set_collector(mock_collector)
    bridge.register_vendor()

    assert "data" in VENDOR_METHODS.get("get_stock_data", {})

    result = route_to_vendor("get_stock_data", "600519.SH", "2024-01-01", "2024-01-31")
    assert "600519" in result
    assert "Total records" in result
    mock_collector.get_kline.assert_awaited_once_with("600519", period="1d", limit=800)


def test_no_foreign_fallback_when_data_vendor_fails():
    """Data vendor failure propagates; foreign vendors are not fallback."""
    from src.agents.data_bridge import DataBridge

    bridge = DataBridge(MagicMock())
    bridge.set_collector(MagicMock())
    bridge.register_vendor()

    def raising_impl(*args, **kwargs):
        raise RuntimeError("data unavailable")

    VENDOR_METHODS["get_stock_data"]["data"] = raising_impl
    VENDOR_METHODS["get_stock_data"]["yfinance"] = MagicMock(return_value="from_yfinance")

    with pytest.raises(RuntimeError, match="data unavailable"):
        route_to_vendor("get_stock_data", "600519.SH", "2024-01-01", "2024-01-31")

    VENDOR_METHODS["get_stock_data"]["yfinance"].assert_not_called()


def test_non_a_share_still_uses_data_collector():
    """Non-A-share tickers still use DataCollector, not foreign vendors."""
    from src.agents.data_bridge import DataBridge

    mock_collector = MagicMock()
    mock_collector.get_kline = AsyncMock(return_value=[
        {
            "date": "2024-01-01",
            "open": 180.0,
            "high": 182.0,
            "low": 179.0,
            "close": 181.0,
            "volume": 10000,
        },
    ])

    bridge = DataBridge(MagicMock())
    bridge.set_collector(mock_collector)
    bridge.register_vendor()

    VENDOR_METHODS["get_stock_data"]["yfinance"] = MagicMock(return_value="from_yfinance")

    result = route_to_vendor("get_stock_data", "AAPL", "2024-01-01", "2024-01-31")
    assert "AAPL" in result
    assert "Total records" in result
    mock_collector.get_kline.assert_awaited_once_with("AAPL", period="1d", limit=800)
    VENDOR_METHODS["get_stock_data"]["yfinance"].assert_not_called()
