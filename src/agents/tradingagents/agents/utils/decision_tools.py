"""Tools for accessing historical trading decisions."""

from typing import Annotated, Optional

from langchain_core.tools import tool


@tool
def get_recent_decisions(
    ticker: Annotated[str, "Ticker symbol to look up historical decisions for"],
    current_price: Annotated[
        Optional[float],
        "Current market price for computing price delta (optional)"
    ] = None,
    current_signal: Annotated[
        Optional[str],
        "Current analysis signal for detecting signal changes (optional)"
    ] = None,
) -> str:
    """Get the 3 most recent final trading decisions for a specific ticker.

    Returns structured records with date, signal, price, and reasoning.
    If current_price and/or current_signal are provided, automatically
    computes price_delta_pct and signal_changed for each record.

    Use this when you need historical context for your decision.
    """
    # Deferred import to avoid circular dependency at module load time
    from tradingagents.agents.utils.memory import TradingMemoryLog
    from tradingagents.dataflows.config import get_config

    config = get_config()
    memory_log = TradingMemoryLog(config)
    records = memory_log.get_recent_decisions(ticker, limit=3)

    if not records:
        return "No historical decisions found for this ticker."

    # Compute deltas when current context is provided
    for r in records:
        if current_price is not None and r.price_at_decision is not None:
            r.price_delta_pct = (
                current_price - r.price_at_decision
            ) / r.price_at_decision
        if current_signal is not None:
            r.signal_changed = r.signal != current_signal

    lines = [f"Recent decisions for {ticker} (most recent first):"]
    for i, r in enumerate(records, 1):
        delta_parts = []
        if r.price_delta_pct is not None:
            delta_parts.append(f"price_delta={r.price_delta_pct:+.1%}")
        if r.signal_changed is not None:
            delta_parts.append(f"signal_changed={r.signal_changed}")
        delta_str = f" | {', '.join(delta_parts)}" if delta_parts else ""
        lines.append(
            f"{i}. [{r.date}] {r.signal} at price={r.price_at_decision}{delta_str}"
        )
        lines.append(f"   Reasoning: {r.reasoning_summary[:200]}")
    return "\n".join(lines)
