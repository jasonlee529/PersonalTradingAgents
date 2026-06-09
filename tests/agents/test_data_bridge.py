import pytest
from unittest.mock import MagicMock, patch


def _vendor_methods_skeleton():
    return {
        "get_stock_data": {},
        "get_indicators": {},
        "get_fundamentals": {},
        "get_balance_sheet": {},
        "get_cashflow": {},
        "get_income_statement": {},
        "get_news": {},
        "get_global_news": {},
        "get_insider_transactions": {},
    }


def test_data_bridge_registers_vendor_methods():
    """DataBridge should register data vendor methods into VENDOR_METHODS."""
    from src.agents.data_bridge import DataBridge

    mock_collector = MagicMock()
    bridge = DataBridge(MagicMock())
    bridge.set_collector(mock_collector)

    with patch.dict(
        "tradingagents.dataflows.interface.VENDOR_METHODS",
        _vendor_methods_skeleton(),
        clear=True,
    ):
        bridge.register_vendor()
        from tradingagents.dataflows.interface import VENDOR_METHODS

        assert "data" in VENDOR_METHODS.get("get_stock_data", {})
        assert "data" in VENDOR_METHODS.get("get_fundamentals", {})
        assert "data" in VENDOR_METHODS.get("get_news", {})


def test_data_bridge_patches_load_ohlcv():
    """DataBridge should monkey-patch stockstats_utils.load_ohlcv."""
    from src.agents.data_bridge import DataBridge
    from tradingagents.dataflows import stockstats_utils

    bridge = DataBridge(MagicMock())
    bridge.set_collector(MagicMock())

    original = stockstats_utils.load_ohlcv
    try:
        bridge.patch_load_ohlcv()
        assert stockstats_utils.load_ohlcv is not original
    finally:
        stockstats_utils.load_ohlcv = original


def test_data_bridge_restore_load_ohlcv():
    """DataBridge should be able to restore the original load_ohlcv."""
    from src.agents.data_bridge import DataBridge
    from tradingagents.dataflows import stockstats_utils

    bridge = DataBridge(MagicMock())
    bridge.set_collector(MagicMock())

    original = stockstats_utils.load_ohlcv
    bridge.patch_load_ohlcv()
    assert stockstats_utils.load_ohlcv is not original

    bridge.restore_load_ohlcv()
    assert stockstats_utils.load_ohlcv is original
    assert not hasattr(bridge, "_original_load_ohlcv")


def test_data_bridge_patch_load_ohlcv_is_idempotent():
    """Repeated patching should still restore the real original function."""
    from src.agents.data_bridge import DataBridge
    from tradingagents.dataflows import stockstats_utils

    bridge = DataBridge(MagicMock())
    bridge.set_collector(MagicMock())

    original = stockstats_utils.load_ohlcv
    try:
        bridge.patch_load_ohlcv()
        first_patch = stockstats_utils.load_ohlcv
        bridge.patch_load_ohlcv()

        assert stockstats_utils.load_ohlcv is first_patch

        bridge.restore_load_ohlcv()
        assert stockstats_utils.load_ohlcv is original
    finally:
        stockstats_utils.load_ohlcv = original


def test_data_bridge_can_unregister_owned_vendor_methods():
    """Only vendor entries installed by this bridge should be removed."""
    from src.agents.data_bridge import DataBridge

    mock_collector = MagicMock()
    bridge = DataBridge(MagicMock())
    bridge.set_collector(mock_collector)

    with patch.dict(
        "tradingagents.dataflows.interface.VENDOR_METHODS",
        _vendor_methods_skeleton(),
        clear=True,
    ):
        from tradingagents.dataflows.interface import VENDOR_METHODS

        bridge.register_vendor()
        installed = VENDOR_METHODS["get_stock_data"]["data"]
        assert installed is not None

        bridge.unregister_vendor()
        assert "data" not in VENDOR_METHODS["get_stock_data"]
