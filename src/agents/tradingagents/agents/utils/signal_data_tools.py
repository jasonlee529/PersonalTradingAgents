"""TradingAgents-facing exports for PersonalTradingAgents signal tools.

The concrete implementations live in ``src.agents.signal_tools`` so all A-share
signal access goes through the same DataCollector-backed path used by the rest
of the application.
"""

from src.agents.signal_tools import (
    SIGNAL_TOOLS,
    get_consensus_expectations,
    get_cross_border_flow,
    get_market_heatmap,
    get_order_flow_profile,
    get_peer_industry_snapshot,
    get_supply_unlock_schedule,
    get_theme_exposure,
    get_trading_seat_activity,
    set_collector,
)

__all__ = [
    "SIGNAL_TOOLS",
    "set_collector",
    "get_consensus_expectations",
    "get_market_heatmap",
    "get_cross_border_flow",
    "get_theme_exposure",
    "get_order_flow_profile",
    "get_trading_seat_activity",
    "get_supply_unlock_schedule",
    "get_peer_industry_snapshot",
]
