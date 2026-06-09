# src/agents/signal_tools.py
"""Market signal tools for the PersonalTradingAgents analysis graph.

Tools provide localized market intelligence for analyst agents.
Each tool attempts to fetch data via DataCollector; falls back to
a friendly message if the data source does not support it.
"""

from typing import Annotated
from langchain_core.tools import tool


# Module-level collector reference — set by TradingAgentsWrapper
_collector = None


def set_collector(collector) -> None:
    """Set the DataCollector instance for signal tools."""
    global _collector
    _collector = collector


# ── Helpers ───────────────────────────────────────────────────────────

def _fallback(name: str) -> str:
    return f"【{name}】当前数据源暂不支持该指标，请在配置中启用信号数据源供应商。"


def _try_call(collector, method: str, *args, **kwargs) -> str:
    """Try calling a collector method; return fallback on any error."""
    if collector is None:
        return _fallback(method)
    fn = getattr(collector, method, None)
    if fn is None:
        return _fallback(method)
    try:
        import asyncio
        if asyncio.iscoroutinefunction(fn):
            # Synchronous wrapper for async methods
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(fn(*args, **kwargs))
            finally:
                loop.close()
        else:
            result = fn(*args, **kwargs)
        if result is None or result == "":
            return _fallback(method)
        if isinstance(result, dict):
            return str(result)
        return str(result)
    except Exception as e:
        return f"【{method}】数据获取失败: {type(e).__name__}。{_fallback(method)}"


# ── Tools ─────────────────────────────────────────────────────────────

@tool
def get_consensus_expectations(
    ticker: Annotated[str, "CN equity code (e.g. 688017)"],
) -> str:
    """
    Retrieve consensus EPS forecasts with forward valuation metrics.
    Returns analyst coverage count, EPS range, forward PE, PEG, and PE digestion time.
    Uses the configured signal_data vendor.
    """
    result = _try_call(_collector, "fetch_consensus_expectations", ticker)
    if result.startswith("【"):
        return result
    return f"【一致预期】股票 {ticker} 的分析师一致预期数据：\n{result}"


@tool
def get_market_heatmap(
    curr_date: Annotated[str, "Date in YYYY-MM-DD format, empty for today"] = "",
) -> str:
    """
    Retrieve today's strong stocks with topic attribution reason tags.
    Shows WHY stocks surged (e.g. '算力租赁+AI政务').
    """
    result = _try_call(_collector, "fetch_market_heatmap", curr_date)
    if result.startswith("【"):
        return result
    return f"【强势股】当日强势股与概念归因：\n{result}"


@tool
def get_cross_border_flow(
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"] = "",
    include_history: Annotated[bool, "Include historical daily data (last 20 trading days)"] = False,
) -> str:
    """
    Retrieve northbound capital flow (沪深股通) data.
    Realtime: minute-level cumulative net buying for HGT + SGT.
    History (optional): daily-level data for trend analysis.
    """
    result = _try_call(_collector, "fetch_cross_border_flow", include_history=include_history)
    if result.startswith("【"):
        return result
    return f"【北向资金】沪深股通资金流向 ({curr_date or '今日'})：\n{result}"


@tool
def get_theme_exposure(
    ticker: Annotated[str, "CN equity code (e.g. 688017)"],
) -> str:
    """
    Retrieve concept/sector/region blocks that a stock belongs to.
    Shows industry (申万), concept themes (e.g. 机器人概念, 减速器), and region.
    """
    result = _try_call(_collector, "fetch_theme_exposure", ticker)
    if result.startswith("【"):
        return result
    return f"【概念板块】{ticker} 所属概念与行业板块：\n{result}"


@tool
def get_order_flow_profile(
    ticker: Annotated[str, "CN equity code"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"] = "",
    include_history: Annotated[bool, "Include historical daily fund flow (last 20 days)"] = True,
) -> str:
    """
    Retrieve individual stock fund flow (main force vs retail investor).
    Realtime: minute-level super/large/medium/small order flow.
    """
    result = _try_call(_collector, "fetch_order_flow_profile", ticker, include_history=include_history)
    if result.startswith("【"):
        return result
    return f"【资金流向】{ticker} 主力资金流向 ({curr_date or '今日'})：\n{result}"


@tool
def get_trading_seat_activity(
    ticker: Annotated[str, "CN equity code (e.g. 000858)"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"] = "",
    look_back_days: Annotated[int, "Days to look back (default 30)"] = 30,
) -> str:
    """
    Retrieve dragon-tiger board (龙虎榜) data for a stock.
    Shows recent LHB appearances, top buyer/seller seats (营业部),
    and institutional involvement.
    """
    result = _try_call(_collector, "fetch_trading_seat_activity", ticker, trade_date=curr_date, look_back_days=look_back_days)
    if result.startswith("【"):
        return result
    return f"【龙虎榜】{ticker} 近 {look_back_days} 日龙虎榜数据 ({curr_date or '今日'})：\n{result}"


@tool
def get_supply_unlock_schedule(
    ticker: Annotated[str, "CN equity code (e.g. 000858)"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"] = "",
    forward_days: Annotated[int, "Days forward to check (default 90)"] = 90,
) -> str:
    """
    Retrieve lockup expiry (限售解禁) schedule for a stock.
    Shows historical unlock records and upcoming expiry calendar
    with impact metrics (unlock quantity, market cap ratio).
    """
    result = _try_call(_collector, "fetch_supply_unlock_schedule", ticker, trade_date=curr_date, forward_days=forward_days)
    if result.startswith("【"):
        return result
    return f"【解禁日历】{ticker} 未来 {forward_days} 日限售解禁计划 ({curr_date or '今日'})：\n{result}"


@tool
def get_peer_industry_snapshot(
    ticker: Annotated[str, "CN equity code (e.g. 000858)"],
    curr_date: Annotated[str, "Date in YYYY-MM-DD format"] = "",
) -> str:
    """
    Retrieve industry sector performance comparison (行业横向对比).
    Shows all 90 THS industries ranked by performance with turnover,
    net capital flow, and leading stocks.
    """
    result = _try_call(_collector, "fetch_peer_industry_snapshot", ticker)
    if result.startswith("【"):
        return result
    return f"【行业对比】{ticker} 所属行业横向对比 ({curr_date or '今日'})：\n{result}"


# ── Tool list for registration ────────────────────────────────────────

SIGNAL_TOOLS = [
    get_consensus_expectations,
    get_market_heatmap,
    get_cross_border_flow,
    get_theme_exposure,
    get_order_flow_profile,
    get_trading_seat_activity,
    get_supply_unlock_schedule,
    get_peer_industry_snapshot,
]


