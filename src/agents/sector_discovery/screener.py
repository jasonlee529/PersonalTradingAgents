"""StockScreener — category-specific stock filtering within sectors.

Each of the five categories uses distinct screening logic:
  热点追逐: momentum + volume breakout + fund flow
  政策前瞻: policy benefit + upstream position + low price
  机构错配: fund entry + low move + fundamental support
  价值蓄势: PEG + R&D + growth (fundamental quality)
  产业链预期差: upstream cold-start + expectation gap evidence

Input: list[SectorSnapshot] from SectorRanker
Output: filtered snapshots with top 3-5 stocks per category.
"""

from __future__ import annotations

import logging

from src.agents.sector_discovery.models import SectorSnapshot, StockSignal

logger = logging.getLogger(__name__)

# Category → max stocks to keep
CATEGORY_LIMITS: dict[str, int] = {
    "热点追逐": 3,
    "政策前瞻": 5,
    "机构错配": 3,
    "价值蓄势": 3,
    "产业链预期差": 3,
}

# Category → minimum score threshold
CATEGORY_THRESHOLDS: dict[str, float] = {
    "热点追逐": 7.0,
    "政策前瞻": 5.0,
    "机构错配": 5.0,
    "价值蓄势": 5.0,
    "产业链预期差": 5.0,
}


def _market_heat_screen(stocks: list[StockSignal], threshold: float, limit: int) -> list[StockSignal]:
    """热点追逐: prefer high momentum + fund flow evidence."""
    scored = []
    for s in stocks:
        if s.score < threshold:
            continue
        bonus = 0.0
        meta = s.metadata or {}
        # Fund flow bonus
        if meta.get("order_flow_profile", 0) > 1e8:
            bonus += 1.0
        # Price momentum bonus
        if meta.get("price_change", 0) > 5:
            bonus += 0.5
        scored.append((s.score + bonus, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in scored[:limit]]


def _policy_screen(stocks: list[StockSignal], threshold: float, limit: int) -> list[StockSignal]:
    """政策前瞻: prefer upstream position + low price + policy level."""
    scored = []
    for s in stocks:
        if s.score < threshold:
            continue
        bonus = 0.0
        meta = s.metadata or {}
        # Upstream position bonus
        if meta.get("position") == "upstream":
            bonus += 1.5
        # Low price movement = more runway
        price_change = abs(meta.get("price_change", 0) or 0)
        if price_change < 5:
            bonus += 1.0
        elif price_change < 10:
            bonus += 0.5
        # High policy level bonus
        if meta.get("policy_level") in ("国务院", "部委"):
            bonus += 1.0
        scored.append((s.score + bonus, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in scored[:limit]]


def _fund_screen(stocks: list[StockSignal], threshold: float, limit: int) -> list[StockSignal]:
    """机构错配: prefer fund new entry + low move + fundamental support."""
    scored = []
    for s in stocks:
        if s.score < threshold:
            continue
        bonus = 0.0
        meta = s.metadata or {}
        # Fund new entry bonus
        if meta.get("is_fund_new", False):
            bonus += 1.5
        if meta.get("fund_count", 0) >= 2:
            bonus += 0.5
        # Low price movement = mismatch
        price_change = abs(meta.get("price_change", 0) or 0)
        if price_change < 5:
            bonus += 1.0
        elif price_change < 10:
            bonus += 0.5
        # Fundamental support: PE reasonable
        pe = meta.get("pe_ttm", 0) or 0
        if 0 < pe < 50:
            bonus += 0.5
        scored.append((s.score + bonus, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in scored[:limit]]


def _value_screen(stocks: list[StockSignal], threshold: float, limit: int) -> list[StockSignal]:
    """价值蓄势: prefer PEG<1 + high R&D + revenue growth + low recognition."""
    scored = []
    for s in stocks:
        if s.score < threshold:
            continue
        bonus = 0.0
        meta = s.metadata or {}
        # PEG < 1
        peg = meta.get("peg", 999)
        if isinstance(peg, (int, float)) and peg < 1:
            bonus += 1.5
        # High R&D intensity
        rd = meta.get("rd_intensity", 0) or 0
        if rd > 0.15:
            bonus += 1.0
        # Revenue growth > 20%
        rev_growth = meta.get("revenue_growth", 0) or 0
        if rev_growth > 0.20:
            bonus += 1.0
        # Low price recognition
        price_change = abs(meta.get("price_change", 0) or 0)
        if price_change < 10:
            bonus += 0.5
        scored.append((s.score + bonus, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in scored[:limit]]


def _chain_screen(stocks: list[StockSignal], threshold: float, limit: int) -> list[StockSignal]:
    """产业链预期差: prefer upstream + high expectation gap + low move."""
    scored = []
    for s in stocks:
        if s.score < threshold:
            continue
        bonus = 0.0
        meta = s.metadata or {}
        # Upstream position
        if meta.get("position") == "upstream":
            bonus += 2.0
        # High expectation gap score
        eg = meta.get("expectation_gap_score", 0) or 0
        if eg >= 7:
            bonus += 1.5
        elif eg >= 5:
            bonus += 0.5
        # Low price movement = cold start
        price_change = abs(meta.get("price_change", 0) or 0)
        if price_change < 5:
            bonus += 1.0
        scored.append((s.score + bonus, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in scored[:limit]]


# Category → screening function
CATEGORY_SCREENS: dict[str, callable] = {
    "热点追逐": _market_heat_screen,
    "政策前瞻": _policy_screen,
    "机构错配": _fund_screen,
    "价值蓄势": _value_screen,
    "产业链预期差": _chain_screen,
}


class StockScreener:
    """Apply category-specific screening to stocks within each sector snapshot."""

    def __init__(
        self,
        limits: dict[str, int] | None = None,
        thresholds: dict[str, float] | None = None,
    ):
        self.limits = limits or CATEGORY_LIMITS.copy()
        self.thresholds = thresholds or CATEGORY_THRESHOLDS.copy()

    def screen(self, snapshots: list[SectorSnapshot]) -> list[SectorSnapshot]:
        """Filter top_stocks in each snapshot based on category rules."""
        result: list[SectorSnapshot] = []
        for snap in snapshots:
            category = snap.tags[0] if snap.tags else "未分类"
            limit = self.limits.get(category, 3)
            threshold = self.thresholds.get(category, 5.0)

            screen_fn = CATEGORY_SCREENS.get(category, _market_heat_screen)
            filtered = screen_fn(snap.top_stocks, threshold, limit)

            if filtered:
                new_snap = SectorSnapshot(
                    board_code=snap.board_code,
                    name=snap.name,
                    change_pct=snap.change_pct,
                    market_heat_score=snap.market_heat_score,
                    policy_score=snap.policy_score,
                    fund_score=snap.fund_score,
                    value_score=snap.value_score,
                    chain_score=snap.chain_score,
                    composite_score=snap.composite_score,
                    expectation_gap_score=snap.expectation_gap_score,
                    tags=snap.tags,
                    top_stocks=filtered,
                    raw_metrics=snap.raw_metrics,
                )
                result.append(new_snap)
                logger.info(
                    "Category %s: screened %d → %d stocks",
                    category,
                    len(snap.top_stocks),
                    len(filtered),
                )
        return result


