from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.models import (
    CandidateDirection,
    DirectionContext,
    SelectedDirection,
    ValidationReport,
)

logger = logging.getLogger(__name__)


class ComparatorAgent:
    """Ranks validated directions and selects top 5."""

    DEFAULT_WEIGHTS = {
        "fund": 0.35,
        "policy": 0.30,
        "sentiment": 0.20,
        "chain_depth": 0.10,
        "catalyst": 0.05,
    }

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS

    def compare(self, context: DirectionContext) -> list[SelectedDirection]:
        """Compare validated directions and select top 5."""
        report_map = {
            r.direction_name: r for r in context.validation_results
        }

        pairs = []
        for cand in context.candidate_directions:
            report = report_map.get(cand.name)
            if report and report.overall_status in ["PASS", "FLAG"]:
                pairs.append((cand, report))

        if not pairs:
            logger.warning("Comparator: no valid directions after filtering")
            return []

        scored = []
        for cand, report in pairs:
            score = self._calculate_score(cand, report)
            scored.append((cand, report, score))

        scored.sort(key=lambda x: x[2], reverse=True)

        selected: list[SelectedDirection] = []
        eliminated_names = [s[0].name for s in scored[5:]]

        for rank, (cand, report, score) in enumerate(scored[:5], 1):
            sel = SelectedDirection(
                name=cand.name,
                rank=rank,
                total_score=round(score, 1),
                fund_score=round(report.fund_validation.score, 1),
                policy_score=round(report.policy_validation.score, 1),
                sentiment_score=round(report.sentiment_validation.score, 1),
                chain_depth_score=self._estimate_chain_depth(cand),
                catalyst_score=self._estimate_catalyst(cand),
                selection_reason=self._build_selection_reason(report),
                comparison_notes=self._build_comparison_notes(cand, report),
                eliminated_peers=eliminated_names if rank == 1 else [],
            )
            selected.append(sel)

        logger.info("Comparator: selected %d directions from %d candidates",
                    len(selected), len(scored))
        return selected

    def _calculate_score(
        self,
        candidate: CandidateDirection,
        report: ValidationReport,
    ) -> float:
        """Calculate weighted composite score."""
        fund = report.fund_validation.score if report.fund_validation.status != "missing" else 0
        policy = report.policy_validation.score if report.policy_validation.status != "missing" else 0
        sentiment = report.sentiment_validation.score if report.sentiment_validation.status != "missing" else 0

        chain_depth = self._estimate_chain_depth(candidate)
        catalyst = self._estimate_catalyst(candidate)

        score = (
            fund * self.weights["fund"] +
            policy * self.weights["policy"] +
            sentiment * self.weights["sentiment"] +
            chain_depth * 10 * self.weights["chain_depth"] +
            catalyst * 10 * self.weights["catalyst"]
        )

        score += report.score_after_validation * 0.2

        return min(10.0, score)

    def _estimate_chain_depth(self, candidate: CandidateDirection) -> float:
        """Estimate chain depth from raw metrics (0-1)."""
        metrics = candidate.raw_metrics or {}
        segments = metrics.get("upstream_segments", [])
        if segments:
            return min(len(segments) / 5, 1.0)
        return 0.3

    def _estimate_catalyst(self, candidate: CandidateDirection) -> float:
        """Estimate catalyst certainty from evidence (0-1)."""
        for sig in candidate.evidence_signals:
            if sig.source in ["policy", "news"]:
                return min(sig.strength / 10, 1.0)
        return 0.2

    def _build_selection_reason(self, report: ValidationReport) -> str:
        """Build human-readable selection reason."""
        parts = []
        if report.fund_validation.status == "strong":
            parts.append("资金强劲")
        if report.policy_validation.status == "strong":
            parts.append("政策支撑")
        if report.sentiment_validation.status == "strong":
            parts.append("情绪积极")
        return "、".join(parts) if parts else "综合评分达标"

    def _build_comparison_notes(
        self,
        candidate: CandidateDirection,
        report: ValidationReport,
    ) -> str:
        """Build comparison notes."""
        notes = []
        if report.fund_validation.status == "strong":
            notes.append("资金面优于同类方向")
        if report.policy_validation.status == "strong":
            notes.append("政策确定性高")
        if report.sentiment_validation.concerns:
            notes.append(f"注意: {report.sentiment_validation.concerns[0]}")
        return "；".join(notes) if notes else ""
