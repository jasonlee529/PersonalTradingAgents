"""Raw-backed lightweight analysis memory.

This is intentionally narrower than the wiki layer. It stores and retrieves
small final-decision records for Portfolio Manager context only.
"""
from __future__ import annotations

from textwrap import shorten
from typing import Any

from src.knowledge.raw_store import RawStore


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def summarize_decision(decision: str, max_chars: int = 1200) -> str:
    text = _clean(decision)
    if not text:
        return ""
    return shorten(text, width=max_chars, placeholder="...")


def extract_rating(decision: str) -> str:
    dl = decision.lower()
    if any(w in dl for w in ["买入", "buy", "加仓"]):
        return "buy"
    if any(w in dl for w in ["卖出", "sell", "清仓"]):
        return "sell"
    if any(w in dl for w in ["减仓", "reduce", "underweight"]):
        return "underweight"
    if any(w in dl for w in ["观望", "watch"]):
        return "watch"
    if any(w in dl for w in ["增持", "overweight"]):
        return "overweight"
    return "hold"


def render_analysis_memory(
    *,
    symbol: str,
    trade_date: str,
    rating: str,
    final_trade_decision: str,
) -> str:
    summary = summarize_decision(final_trade_decision)
    return "\n".join(
        [
            f"# {symbol} {trade_date} Analysis Memory",
            "",
            "## Final Decision",
            "",
            f"Rating: {rating}",
            "",
            summary or "(empty decision)",
            "",
            "## Outcome",
            "",
            "pending",
            "",
            "## Reflection",
            "",
            "pending",
        ]
    )


async def save_analysis_memory(
    raw_store: RawStore,
    *,
    symbol: str,
    trade_date: str,
    run_id: str,
    run_time: str,
    final_trade_decision: str,
    linked_full_report_source_id: str = "",
) -> dict | None:
    """Persist one lightweight final-decision memory record in raw."""
    if not final_trade_decision:
        return None

    rating = extract_rating(final_trade_decision)
    return await raw_store.add_source(
        source_kind="analysis_memory",
        origin="agent",
        title=f"{symbol} {trade_date} Analysis Memory",
        markdown=render_analysis_memory(
            symbol=symbol,
            trade_date=trade_date,
            rating=rating,
            final_trade_decision=final_trade_decision,
        ),
        metadata={
            "symbol": symbol,
            "symbols": [symbol],
            "trade_date": trade_date,
            "run_id": run_id,
            "run_time": run_time,
            "analysis_node": "portfolio_memory",
            "agent_flow": "trading_agents",
            "rating": rating,
            "raw_return": None,
            "alpha_return": None,
            "outcome_status": "pending",
            "reflection_status": "pending",
            "linked_full_report_source_id": linked_full_report_source_id,
            "tags": [f"stock/{symbol}", "memory/analysis"],
        },
    )


async def load_raw_memory_context(
    raw_store: RawStore,
    symbol: str,
    *,
    limit: int = 5,
    max_chars_per_entry: int = 900,
) -> str:
    """Load recent same-symbol raw memory entries for prompt injection."""
    rows = await raw_store.list_sources(
        source_kind="analysis_memory",
        symbol=symbol,
        limit=max(1, min(limit, 20)),
    )
    if not rows:
        return ""

    parts: list[str] = [f"Past analyses of {symbol} (most recent first):"]
    for row in rows[:limit]:
        source = await raw_store.read_source(row["source_id"])
        metadata: dict[str, Any] = source.get("metadata") or {}
        rating = metadata.get("rating") or "unknown"
        trade_date = source.get("trade_date") or metadata.get("trade_date") or ""
        markdown = source.get("markdown", "")
        body = summarize_decision(markdown, max_chars=max_chars_per_entry)
        parts.append(f"[{trade_date} | {symbol} | {rating}]\n{body}")
    return "\n\n".join(parts)
