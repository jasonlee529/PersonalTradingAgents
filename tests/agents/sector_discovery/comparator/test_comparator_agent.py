import pytest

from src.agents.sector_discovery.comparator.comparator_agent import ComparatorAgent
from src.agents.sector_discovery.models import (
    CandidateDirection,
    DirectionContext,
    ValidationReport,
    DimensionValidation,
    SelectedDirection,
)


class TestComparatorAgent:
    @pytest.fixture
    def agent(self):
        return ComparatorAgent()

    def test_compare_selects_top_5(self, agent):
        context = DirectionContext(date="2026-06-04")
        for i in range(8):
            cand = CandidateDirection(
                name=f"方向{i}",
                category="热点追逐",
                confidence=8.0 - i * 0.5,
            )
            report = ValidationReport(
                direction_name=cand.name,
                overall_status="PASS" if i < 6 else "REJECT",
                fund_validation=DimensionValidation(
                    dimension="fund", status="strong", score=8.0 - i
                ),
                policy_validation=DimensionValidation(
                    dimension="policy", status="strong", score=8.0 - i
                ),
                sentiment_validation=DimensionValidation(
                    dimension="sentiment", status="moderate", score=6.0
                ),
                score_after_validation=7.0 - i * 0.5,
            )
            context.candidate_directions.append(cand)
            context.validation_results.append(report)

        selected = agent.compare(context)

        assert len(selected) <= 5
        assert all(isinstance(s, SelectedDirection) for s in selected)
        assert selected[0].rank == 1

    def test_compare_with_all_rejected(self, agent):
        context = DirectionContext(date="2026-06-04")
        for i in range(3):
            cand = CandidateDirection(name=f"方向{i}", category="热点追逐", confidence=5.0)
            report = ValidationReport(
                direction_name=cand.name,
                overall_status="REJECT",
                score_after_validation=2.0,
            )
            context.candidate_directions.append(cand)
            context.validation_results.append(report)

        selected = agent.compare(context)
        assert len(selected) == 0

    def test_eliminated_peers_tracked(self, agent):
        context = DirectionContext(date="2026-06-04")
        for i in range(6):
            cand = CandidateDirection(name=f"方向{i}", category="热点追逐", confidence=8.0)
            report = ValidationReport(
                direction_name=cand.name,
                overall_status="PASS",
                score_after_validation=8.0 - i * 0.3,
            )
            context.candidate_directions.append(cand)
            context.validation_results.append(report)

        selected = agent.compare(context)

        if selected:
            assert len(selected[0].eliminated_peers) > 0 or len(selected) == 6
