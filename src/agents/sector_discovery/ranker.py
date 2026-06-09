"""SectorRanker — 7-dimension scoring with expectation-gap bonus.

Input: list[SectorSnapshot] from SectorAggregator
Output: re-scored and sorted snapshots, top 5 per category.

Seven independent dimensions:
  1. order_flow_profile       — main-force net inflow (from raw_metrics)
  2. news_heat       — keyword frequency in news (from raw_metrics)
  3. limit_up        — limit-up stock ratio (from raw_metrics)
  4. dragon_tiger    — dragon-tiger board appearances (from raw_metrics)
  5. fund_holdings   — fund new/increased positions (from raw_metrics)
  6. trend           — 3-day fund-flow slope (from raw_metrics)
  7. expectation_gap — chain position deviation + market lag (from snapshot)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from src.agents.sector_discovery.models import SectorSnapshot

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "order_flow_profile": 1.0,
    "news_heat": 0.8,
    "limit_up": 0.8,
    "dragon_tiger": 0.6,
    "fund_holdings": 1.0,
    "trend": 0.8,
    "expectation_gap": 1.5,  # higher weight for expectation gap
}


class SectorRanker:
    """Score and rank sector snapshots across 7 dimensions."""

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def rank(self, snapshots: list[SectorSnapshot]) -> list[SectorSnapshot]:
        """Re-score snapshots and return top 5 per category."""
        if not snapshots:
            return []

        # 1. Re-score every snapshot with weighted 7-dimension sum
        for snap in snapshots:
            snap.composite_score = self._compute_weighted_score(snap)

        # 2. Group by dominant category tag (first tag)
        by_category: dict[str, list[SectorSnapshot]] = defaultdict(list)
        for snap in snapshots:
            category = snap.tags[0] if snap.tags else "未分类"
            by_category[category].append(snap)

        # 3. Sort each category independently, take top 5
        ranked: list[SectorSnapshot] = []
        for category, items in by_category.items():
            items.sort(key=lambda s: s.composite_score, reverse=True)
            ranked.extend(items[:5])
            logger.info(
                "Category %s: %d snapshots, top score %.1f",
                category,
                len(items),
                items[0].composite_score if items else 0.0,
            )

        # 4. Final sort by composite score across all categories
        ranked.sort(key=lambda s: s.composite_score, reverse=True)
        return ranked

    def _compute_weighted_score(self, snap: SectorSnapshot) -> float:
        total = 0.0
        weight_sum = 0.0
        metrics = snap.raw_metrics

        for dim, weight in self.weights.items():
            score = 0.0
            if dim == "order_flow_profile":
                score = self._fetch_order_flow_profile_score(snap, metrics)
            elif dim == "news_heat":
                score = self._get_news_heat_score(snap, metrics)
            elif dim == "limit_up":
                score = self._get_limit_up_score(snap, metrics)
            elif dim == "dragon_tiger":
                score = self._get_dragon_tiger_score(snap, metrics)
            elif dim == "fund_holdings":
                score = self._get_fund_holdings_score(snap, metrics)
            elif dim == "trend":
                score = self._get_trend_score(snap, metrics)
            elif dim == "expectation_gap":
                score = snap.expectation_gap_score

            total += score * weight
            weight_sum += weight

        if weight_sum == 0:
            return 0.0
        return round(min(total / weight_sum, 10.0), 1)

    # ── Individual dimension scorers ──────────────────────────────────────

    def _fetch_order_flow_profile_score(self, snap: SectorSnapshot, metrics: dict) -> float:
        """Main-force net inflow score (0-10)."""
        if "order_flow_profile" in metrics:
            val = metrics["order_flow_profile"]
            if isinstance(val, (int, float)):
                # Normalize: 1亿 = 5分, 3亿 = 8分, 5亿+ = 10分
                return min(10.0, max(0.0, val / 1e8 * 2))
        # Fallback to market_heat_score as proxy
        return snap.market_heat_score

    def _get_news_heat_score(self, snap: SectorSnapshot, metrics: dict) -> float:
        """News keyword frequency score (0-10)."""
        if "news_count" in metrics:
            val = metrics["news_count"]
            if isinstance(val, (int, float)):
                return min(10.0, val * 2)
        # Fallback to policy_score as proxy (policy drives news)
        return snap.policy_score

    def _get_limit_up_score(self, snap: SectorSnapshot, metrics: dict) -> float:
        """Limit-up stock ratio score (0-10)."""
        if "limit_up_count" in metrics and "board_stock_count" in metrics:
            count = metrics["limit_up_count"]
            total = metrics["board_stock_count"]
            if total and isinstance(count, (int, float)) and isinstance(total, (int, float)):
                ratio = count / total
                return min(10.0, ratio * 50)  # 20% limit-up = 10分
        # Fallback to market_heat_score as proxy
        return snap.market_heat_score

    def _get_dragon_tiger_score(self, snap: SectorSnapshot, metrics: dict) -> float:
        """Dragon-tiger board appearance score (0-10)."""
        if "dragon_tiger_count" in metrics:
            val = metrics["dragon_tiger_count"]
            if isinstance(val, (int, float)):
                return min(10.0, val * 2)
        # Fallback to market_heat_score as proxy
        return snap.market_heat_score * 0.6

    def _get_fund_holdings_score(self, snap: SectorSnapshot, metrics: dict) -> float:
        """Fund new/increased position score (0-10)."""
        if "fund_new_count" in metrics:
            val = metrics["fund_new_count"]
            if isinstance(val, (int, float)):
                return min(10.0, val * 3)
        # Fallback to fund_score
        return snap.fund_score

    def _get_trend_score(self, snap: SectorSnapshot, metrics: dict) -> float:
        """3-day fund-flow slope score (0-10)."""
        if "order_flow_profile_slope" in metrics:
            val = metrics["order_flow_profile_slope"]
            if isinstance(val, (int, float)):
                # Positive slope = increasing inflow = good
                return min(10.0, max(0.0, 5.0 + val * 5.0))
        # Fallback to composite_score trend proxy
        return snap.composite_score * 0.8


