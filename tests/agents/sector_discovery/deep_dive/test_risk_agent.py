import pytest
from unittest.mock import MagicMock

from src.agents.sector_discovery.deep_dive.risk_agent import RiskAgent
from src.agents.sector_discovery.models import (
    SelectedDirection,
    DirectionContext,
    ValidationReport,
    DimensionValidation,
)


class TestRiskAgent:
    @pytest.fixture
    def agent(self):
        return RiskAgent(MagicMock(), MagicMock(), MagicMock())

    @pytest.fixture
    def direction(self):
        return SelectedDirection(name="固态电池", rank=1, total_score=8.7)

    @pytest.mark.asyncio
    async def test_analyze_returns_assessment(self, agent, direction):
        context = DirectionContext(date="2026-06-04")
        assessment = await agent.analyze(direction, context)

        assert assessment.direction_name == "固态电池"
        assert assessment.overall_risk_level in ["low", "moderate", "high"]
        assert len(assessment.invalidation_conditions) > 0

    @pytest.mark.asyncio
    async def test_high_sentiment_concern_increases_risk(self, agent, direction):
        context = DirectionContext(date="2026-06-04")
        report = ValidationReport(
            direction_name="固态电池",
            overall_status="PASS",
            sentiment_validation=DimensionValidation(
                dimension="sentiment",
                status="moderate",
                score=6.0,
                concerns=["舆情过热"],
            ),
        )
        context.validation_results.append(report)

        assessment = await agent.analyze(direction, context)
        assert assessment.overall_risk_level in ["moderate", "high"]
