import logging
from src.config import Settings
from src.agents.wrapper.patches import ManagedPatch, PatchRegistry

logger = logging.getLogger(__name__)


class DataBridge:
    """Bridge between our data layer and TradingAgents tool interface.

    1. Register 'data' vendor methods into TradingAgents' VENDOR_METHODS.
    2. Monkey-patch stockstats_utils.load_ohlcv so indicator calculations
       use our K-line data for CN tickers.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._collector = None
        self._registry = PatchRegistry()
        self._registry.register(
            ManagedPatch(
                patch_id="data_bridge.vendor_methods",
                apply=self._register_vendor_impl,
                restore=self.unregister_vendor,
                is_applied=self._vendor_registered,
            )
        )
        self._registry.register(
            ManagedPatch(
                patch_id="data_bridge.load_ohlcv",
                apply=self._patch_load_ohlcv_impl,
                restore=self.restore_load_ohlcv,
                is_applied=self._load_ohlcv_patched,
            )
        )

    def set_collector(self, collector) -> None:
        self._collector = collector

    def _ensure_collector(self):
        if self._collector is None:
            raise RuntimeError("DataBridge: collector not wired")

    def register_vendor(self) -> None:
        self._registry.apply("data_bridge.vendor_methods")

    def _register_vendor_impl(self) -> None:
        self._ensure_collector()
        from src.agents.data_vendor import DataVendor
        from tradingagents.dataflows.interface import VENDOR_METHODS

        vendor = DataVendor(self._collector)
        self._registered_vendor_methods = {}
        methods = {
            "get_stock_data": vendor.get_stock_data,
            "get_indicators": vendor.get_indicators,
            "get_fundamentals": vendor.get_fundamentals,
            "get_balance_sheet": vendor.get_balance_sheet,
            "get_cashflow": vendor.get_cashflow,
            "get_income_statement": vendor.get_income_statement,
            "get_news": vendor.get_news,
            "get_global_news": vendor.get_global_news,
            "get_insider_transactions": vendor.get_insider_transactions,
        }
        for method_name, impl in methods.items():
            if method_name in VENDOR_METHODS and "data" not in VENDOR_METHODS[method_name]:
                VENDOR_METHODS[method_name]["data"] = impl
                self._registered_vendor_methods[method_name] = impl
                logger.debug("Registered data for '%s'", method_name)

    def unregister_vendor(self) -> None:
        registered = getattr(self, "_registered_vendor_methods", None)
        if not registered:
            return
        from tradingagents.dataflows.interface import VENDOR_METHODS

        for method_name, impl in list(registered.items()):
            if VENDOR_METHODS.get(method_name, {}).get("data") is impl:
                del VENDOR_METHODS[method_name]["data"]
                logger.debug("Unregistered data for '%s'", method_name)
        delattr(self, "_registered_vendor_methods")

    def _vendor_registered(self) -> bool:
        return bool(getattr(self, "_registered_vendor_methods", None))

    def patch_load_ohlcv(self) -> None:
        self._registry.apply("data_bridge.load_ohlcv")

    def _patch_load_ohlcv_impl(self) -> None:
        self._ensure_collector()
        from src.agents.data_vendor import DataVendor
        from tradingagents.dataflows import stockstats_utils

        vendor = DataVendor(self._collector)
        def _patched_load_ohlcv(symbol: str, curr_date: str):
            try:
                return vendor.load_ohlcv(symbol, curr_date)
            except Exception as e:
                logger.warning("DataVendor load_ohlcv failed for %s: %s", symbol, e)
                import pandas as pd
                return pd.DataFrame()

        self._original_load_ohlcv = stockstats_utils.load_ohlcv
        stockstats_utils.load_ohlcv = _patched_load_ohlcv
        self._patched_load_ohlcv = _patched_load_ohlcv
        logger.info("Patched stockstats_utils.load_ohlcv for DataCollector-only data")

    def restore_load_ohlcv(self) -> None:
        if hasattr(self, "_original_load_ohlcv"):
            from tradingagents.dataflows import stockstats_utils
            if stockstats_utils.load_ohlcv is getattr(self, "_patched_load_ohlcv", None):
                stockstats_utils.load_ohlcv = self._original_load_ohlcv
            delattr(self, "_original_load_ohlcv")
            if hasattr(self, "_patched_load_ohlcv"):
                delattr(self, "_patched_load_ohlcv")
            logger.info("Restored original stockstats_utils.load_ohlcv")

    def _load_ohlcv_patched(self) -> bool:
        try:
            from tradingagents.dataflows import stockstats_utils
        except Exception:
            return False
        return (
            hasattr(self, "_patched_load_ohlcv")
            and stockstats_utils.load_ohlcv is self._patched_load_ohlcv
        )

    def restore_patches(self) -> None:
        self._registry.restore_all()
