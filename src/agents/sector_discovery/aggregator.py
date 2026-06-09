"""SectorAggregator — merge multi-dimensional scan results and classify."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from src.agents.sector_discovery.models import SectorSnapshot, StockSignal
from src.agents.sector_discovery.scanners.base import ScanResult

logger = logging.getLogger(__name__)

# Category tags based on dominant signal pattern
CATEGORY_MARKET_HEAT = "热点追逐"
CATEGORY_POLICY = "政策前瞻"
CATEGORY_FUND = "机构错配"
CATEGORY_VALUE = "价值蓄势"
CATEGORY_CHAIN = "产业链预期差"
CATEGORY_NEWS = "新闻催化"
CATEGORY_CORRECTION = "回调低吸"
CATEGORY_MOMENTUM = "趋势动能"

# Dimension → default category mapping
DIMENSION_CATEGORY: dict[str, str] = {
    "market_heat": CATEGORY_MARKET_HEAT,
    "policy": CATEGORY_POLICY,
    "fund": CATEGORY_FUND,
    "value": CATEGORY_VALUE,
    "chain": CATEGORY_CHAIN,
    "news": CATEGORY_NEWS,
    "correction": CATEGORY_CORRECTION,
    "momentum": CATEGORY_MOMENTUM,
}

# Cross-validation boost per additional dimension
CROSS_VALIDATION_BOOST = 1.5


@dataclass
class _StockAggregate:
    """Internal accumulator for a single stock across dimensions."""

    symbol: str
    name: str = ""
    dimension_scores: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    catalysts: list[str] = field(default_factory=list)
    time_horizons: list[str] = field(default_factory=list)
    metadatas: list[dict] = field(default_factory=list)  # per-dimension raw metrics

    @property
    def composite_score(self) -> float:
        if not self.dimension_scores:
            return 0.0
        base = sum(self.dimension_scores.values()) / len(self.dimension_scores)
        dim_count = len(self.dimension_scores)
        dim_boost = 1.0 + (dim_count - 1) * CROSS_VALIDATION_BOOST
        cv_boost = self.cross_validation_boost
        return round(min(base * dim_boost + cv_boost, 10.0), 1)

    @property
    def cross_validation_boost(self) -> float:
        """Multi-dimension intersection boosts confidence."""
        dims = set(self.dimension_scores.keys())
        boost = 0.0
        # Policy + Chain = strong logical coherence
        if "policy" in dims and "chain" in dims:
            boost += 2.0
        # Fund + Value = fundamental support
        if "fund" in dims and "value" in dims:
            boost += 1.5
        # Three or more dimensions = high confidence
        if len(dims) >= 3:
            boost += 1.0
        # Four or more dimensions = very high confidence
        if len(dims) >= 4:
            boost += 0.5
        # News + Chain = narrative support
        if "news" in dims and "chain" in dims:
            boost += 1.5
        # News + Policy = policy narrative confirmation
        if "news" in dims and "policy" in dims:
            boost += 1.5
        # Correction + Value = value at discount
        if "correction" in dims and "value" in dims:
            boost += 1.0
        return boost

    @property
    def expectation_gap_score(self) -> float:
        """Higher when policy/chain signals dominate and market_heat is low."""
        hot = self.dimension_scores.get("market_heat", 0)
        policy = self.dimension_scores.get("policy", 0)
        chain = self.dimension_scores.get("chain", 0)
        fund = self.dimension_scores.get("fund", 0)
        value = self.dimension_scores.get("value", 0)
        # Low heat + high policy/chain/fund/value = high expectation gap
        gap = max(policy, chain, fund, value) - hot * 0.5
        return round(max(0, min(gap, 10)), 1)

    @property
    def dominant_category(self) -> str:
        """Pick category based on highest dimension score."""
        if not self.dimension_scores:
            return "未分类"
        best_dim = max(self.dimension_scores, key=self.dimension_scores.get)
        return DIMENSION_CATEGORY.get(best_dim, "未分类")

    def to_stock_signal(self) -> StockSignal:
        # Merge all metadata dicts
        merged_meta: dict = {}
        for m in self.metadatas:
            merged_meta.update(m)
        return StockSignal(
            symbol=self.symbol,
            name=self.name,
            score=self.composite_score,
            dimension="aggregate",
            reason="; ".join(self.reasons)[:200],
            catalyst="; ".join(self.catalysts)[:100] if self.catalysts else "",
            time_horizon=self._pick_time_horizon(),
            metadata=merged_meta,
        )

    def _pick_time_horizon(self) -> str:
        if "short" in self.time_horizons:
            return "short"
        if "long" in self.time_horizons:
            return "long"
        return "medium"


class SectorAggregator:
    """Merge multi-dimensional stock signals into classified sector snapshots."""

    def aggregate(self, stock_signals: list[StockSignal]) -> list[SectorSnapshot]:
        if not stock_signals:
            return []

        # 1. Flatten and accumulate per-stock across dimensions
        stock_map: dict[str, _StockAggregate] = {}
        for signal in stock_signals:
            agg = stock_map.setdefault(signal.symbol, _StockAggregate(symbol=signal.symbol))
            if signal.name:
                agg.name = signal.name
            agg.dimension_scores[signal.dimension] = signal.score
            if signal.reason:
                agg.reasons.append(signal.reason)
            if signal.catalyst:
                agg.catalysts.append(signal.catalyst)
            if signal.time_horizon:
                agg.time_horizons.append(signal.time_horizon)
            if signal.metadata:
                agg.metadatas.append(signal.metadata)

        if not stock_map:
            return []

        # 2. Group by dominant category
        category_groups: dict[str, list[_StockAggregate]] = defaultdict(list)
        for agg in stock_map.values():
            category_groups[agg.dominant_category].append(agg)

        # 3. Build SectorSnapshot per category
        snapshots: list[SectorSnapshot] = []
        for category, aggs in category_groups.items():
            aggs.sort(key=lambda a: a.composite_score, reverse=True)
            top = [a.to_stock_signal() for a in aggs[:10]]
            avg_gap = sum(a.expectation_gap_score for a in aggs) / len(aggs) if aggs else 0.0
            avg_composite = sum(a.composite_score for a in aggs) / len(aggs) if aggs else 0.0

            # Aggregate raw_metrics across all stocks in this category
            raw_metrics: dict = {}
            for agg in aggs:
                for m in agg.metadatas:
                    for k, v in m.items():
                        if k not in raw_metrics:
                            raw_metrics[k] = []
                        if isinstance(v, list):
                            raw_metrics[k].extend(v)
                        else:
                            raw_metrics[k].append(v)
            # Average numeric metrics; flatten list-of-lists for string metrics
            for k, vals in raw_metrics.items():
                if vals and all(isinstance(x, (int, float)) for x in vals):
                    raw_metrics[k] = sum(vals) / len(vals)
                elif vals and all(isinstance(x, str) for x in vals):
                    raw_metrics[k] = list(dict.fromkeys(vals))  # dedup preserve order

            snapshot = SectorSnapshot(
                board_code="",
                name=f"{category} 方向",
                tags=[category],
                top_stocks=top,
                composite_score=round(avg_composite, 1),
                expectation_gap_score=round(avg_gap, 1),
                raw_metrics=raw_metrics,
            )
            # Set per-dimension scores from the group average
            for dim in ["market_heat", "policy", "fund", "value", "chain", "news", "correction", "momentum"]:
                dim_scores = [a.dimension_scores.get(dim, 0) for a in aggs]
                avg = sum(dim_scores) / len(dim_scores) if dim_scores else 0.0
                setattr(snapshot, f"{dim}_score", round(avg, 1))
            snapshots.append(snapshot)

        snapshots.sort(key=lambda s: s.composite_score, reverse=True)
        return snapshots

