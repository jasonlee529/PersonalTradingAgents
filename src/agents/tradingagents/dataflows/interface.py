# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "data",
]

# Mapping of methods to their vendor-specific implementations.
# The in-repo DataBridge registers the "data" implementation for every method
# at runtime. Do not register yfinance/alpha_vantage here: analysis data must
# stay on DataCollector and its configured domestic sources only.
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {},
    # technical_indicators
    "get_indicators": {},
    # fundamental_data
    "get_fundamentals": {},
    "get_balance_sheet": {},
    "get_cashflow": {},
    "get_income_statement": {},
    # news_data
    "get_news": {},
    "get_global_news": {},
    "get_insider_transactions": {},
}

def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "data")

def _is_a_share(ticker: str) -> bool:
    """Detect A-share ticker (6-digit code starting with 0, 3, or 6)."""
    s = ticker.strip().upper()
    if "." in s:
        s = s.split(".")[0]
    return len(s) == 6 and s.isdigit() and s[0] in ("0", "3", "6")


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to DataCollector-backed vendor only.

    Foreign vendors are intentionally not registered here. If "data" is not
    configured or unavailable, fail fast instead of falling back to yfinance or
    alpha_vantage.
    """
    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)
    configured_vendors = [v.strip() for v in vendor_config.split(",") if v.strip()]
    if not configured_vendors:
        configured_vendors = ["data"]

    blocked = [v for v in configured_vendors if v != "data"]
    if blocked:
        raise RuntimeError(
            f"Foreign or unsupported data vendor configured for '{method}': {blocked}. "
            "Only 'data' is allowed."
        )

    for vendor in configured_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl

        return impl_func(*args, **kwargs)

    raise RuntimeError(
        f"No DataCollector vendor registered for '{method}'. "
        "DataBridge.register_vendor() must run before analysis."
    )
