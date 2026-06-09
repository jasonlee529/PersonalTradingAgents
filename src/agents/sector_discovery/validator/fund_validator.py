from __future__ import annotations

import logging

from src.agents.sector_discovery.models import CandidateDirection, DimensionValidation

logger = logging.getLogger(__name__)


class FundValidator:
    """Validates fund flow dimension for a candidate direction."""

    def validate(self, candidate: CandidateDirection) -> DimensionValidation:
        """Validate fund dimension based on raw metrics."""
        metrics = candidate.raw_metrics or {}
        order_flow_profile = metrics.get("order_flow_profile", 0)
        limit_up = metrics.get("limit_up_count", 0)

        # Fallback: infer limit_up from evidence_signals if raw_metrics missing
        if limit_up == 0:
            for sig in candidate.evidence_signals:
                if sig.source == "market_heat":
                    market_heatmap = sig.data_snapshot.get("market_heatmap", [])
                    limit_up = max(limit_up, len(market_heatmap))

        # Missing data
        if order_flow_profile == 0 and limit_up == 0:
            return DimensionValidation(
                dimension="fund",
                status="missing",
                score=0.0,
                evidence="无资金流向数据",
            )

        score = 0.0
        evidence_parts = []
        concerns = []

        # Fund flow scoring
        if order_flow_profile > 1e9:
            score += 4.0
            evidence_parts.append(f"主力净流入 {order_flow_profile/1e8:.1f} 亿")
        elif order_flow_profile > 5e8:
            score += 3.0
            evidence_parts.append(f"主力净流入 {order_flow_profile/1e8:.1f} 亿")
        elif order_flow_profile > 0:
            score += 1.5
            evidence_parts.append(f"主力净流入 {order_flow_profile/1e8:.1f} 亿")
        elif order_flow_profile < -5e8:
            score -= 2.0
            evidence_parts.append(f"主力净流出 {abs(order_flow_profile)/1e8:.1f} 亿")
            concerns.append("资金大幅流出")

        # Limit up scoring
        if limit_up >= 5:
            score += 3.0
            evidence_parts.append(f"涨停 {limit_up} 家")
        elif limit_up >= 3:
            score += 2.0
            evidence_parts.append(f"涨停 {limit_up} 家")
        elif limit_up > 0:
            score += 1.0
            evidence_parts.append(f"涨停 {limit_up} 家")

        # Heat level from evidence signals
        for sig in candidate.evidence_signals:
            if sig.source == "market_heat":
                heat = sig.data_snapshot.get("heat_level", 0)
                if heat >= 8:
                    score += 2.0
                    evidence_parts.append("热点强度高")
                elif heat >= 5:
                    score += 1.0

        score = max(0.0, min(10.0, score))

        if score >= 7:
            status = "strong"
        elif score >= 4:
            status = "moderate"
        else:
            status = "weak"
            concerns.append("资金信号偏弱")

        return DimensionValidation(
            dimension="fund",
            status=status,
            score=score,
            evidence="；".join(evidence_parts) if evidence_parts else "资金数据不足",
            concerns=concerns,
        )


