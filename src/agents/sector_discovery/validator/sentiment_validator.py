from __future__ import annotations

import logging

from src.agents.sector_discovery.models import CandidateDirection, DimensionValidation

logger = logging.getLogger(__name__)


class SentimentValidator:
    """Validates market sentiment dimension for a candidate direction."""

    def validate(self, candidate: CandidateDirection) -> DimensionValidation:
        """Validate sentiment dimension."""
        metrics = candidate.raw_metrics or {}
        news_heat = metrics.get("news_heat", 0)
        limit_up = metrics.get("limit_up_count", 0)

        # Fallback: infer limit_up from evidence_signals if raw_metrics missing
        if limit_up == 0:
            for sig in candidate.evidence_signals:
                if sig.source == "market_heat":
                    market_heatmap = sig.data_snapshot.get("market_heatmap", [])
                    limit_up = max(limit_up, len(market_heatmap))

        score = 0.0
        evidence_parts = []
        concerns = []

        if news_heat >= 8:
            score += 2.0
            evidence_parts.append(f"舆情热度高 ({news_heat})")
            concerns.append("舆情过热，需警惕情绪退潮")
        elif news_heat >= 5:
            score += 3.5
            evidence_parts.append(f"舆情热度适中 ({news_heat})")
        elif news_heat > 0:
            score += 2.0
            evidence_parts.append(f"舆情有热度 ({news_heat})")

        if limit_up >= 5:
            score += 3.0
            evidence_parts.append(f"涨停 {limit_up} 家，情绪强劲")
        elif limit_up >= 3:
            score += 2.5
            evidence_parts.append(f"涨停 {limit_up} 家")
        elif limit_up > 0:
            score += 1.5
            evidence_parts.append(f"涨停 {limit_up} 家")

        for sig in candidate.evidence_signals:
            if sig.source == "market_heat":
                market_heatmap = sig.data_snapshot.get("market_heatmap", [])
                if len(market_heatmap) >= 3:
                    score += 2.0
                    evidence_parts.append(f"多股联动 ({len(market_heatmap)})")
                elif len(market_heatmap) > 0:
                    score += 1.0

        if news_heat >= 9 and limit_up >= 8:
            score -= 2.0
            concerns.append("情绪严重过热，短期回调风险大")

        score = max(0.0, min(10.0, score))

        if score >= 7:
            status = "strong"
        elif score >= 4:
            status = "moderate"
        else:
            status = "weak"
            concerns.append("情绪面偏弱")

        return DimensionValidation(
            dimension="sentiment",
            status=status,
            score=score,
            evidence="；".join(evidence_parts) if evidence_parts else "情绪数据不足",
            concerns=concerns,
        )


