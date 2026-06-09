from __future__ import annotations

import logging

from src.agents.sector_discovery.models import CandidateDirection, DimensionValidation

logger = logging.getLogger(__name__)


class PolicyValidator:
    """Validates policy dimension for a candidate direction."""

    LEVEL_SCORES = {
        "中央": 4.0,
        "部委": 3.0,
        "地方": 1.5,
    }

    def validate(self, candidate: CandidateDirection) -> DimensionValidation:
        """Validate policy dimension based on raw metrics."""
        metrics = candidate.raw_metrics or {}
        policy_level = metrics.get("policy_level", "")

        has_policy_signal = any(
            sig.source == "policy" for sig in candidate.evidence_signals
        )

        if not policy_level and not has_policy_signal:
            return DimensionValidation(
                dimension="policy",
                status="missing",
                score=0.0,
                evidence="无政策信号",
            )

        score = 0.0
        evidence_parts = []
        concerns = []

        level_score = self.LEVEL_SCORES.get(policy_level, 0)
        score += level_score
        if policy_level:
            evidence_parts.append(f"{policy_level}级政策")

        industries = metrics.get("beneficiary_industries", [])
        if industries:
            score += 2.0
            evidence_parts.append(f"受益产业: {', '.join(industries[:3])}")

        time_window = metrics.get("policy_time_window", "")
        if time_window == "immediate":
            score += 2.0
            evidence_parts.append("即刻生效")
        elif time_window in ["short", "medium"]:
            score += 1.5
            evidence_parts.append("近期生效")
        elif time_window == "annual":
            score += 1.0

        for sig in candidate.evidence_signals:
            if sig.source == "policy":
                score += min(sig.strength / 3, 2.0)

        score = max(0.0, min(10.0, score))

        if score >= 7:
            status = "strong"
        elif score >= 4:
            status = "moderate"
        else:
            status = "weak"
            concerns.append("政策确定性不足")

        return DimensionValidation(
            dimension="policy",
            status=status,
            score=score,
            evidence="；".join(evidence_parts) if evidence_parts else "政策数据不足",
            concerns=concerns,
        )
