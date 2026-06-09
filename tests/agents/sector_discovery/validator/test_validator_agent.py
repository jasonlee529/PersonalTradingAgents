import pytest
from unittest.mock import MagicMock

from src.agents.sector_discovery.validator.validator_agent import ValidatorAgent
from src.agents.sector_discovery.models import (
    CandidateDirection,
    DirectionContext,
    ValidationReport,
)


class TestValidatorAgent:
    @pytest.fixture
    def agent(self):
        return ValidatorAgent(MagicMock(), MagicMock(), MagicMock())

    def test_validate_candidate_pass(self, agent):
        candidate = CandidateDirection(
            name="固态电池",
            category="热点追逐",
            confidence=8.0,
            raw_metrics={"order_flow_profile": 1.2e9, "policy_level": "中央", "news_heat": 6},
        )
        context = DirectionContext(date="2026-06-04")
        report = agent.validate(candidate, context)

        assert isinstance(report, ValidationReport)
        assert report.direction_name == "固态电池"
        assert report.overall_status in ["PASS", "FLAG", "REJECT"]
        assert report.fund_validation.dimension == "fund"
        assert report.policy_validation.dimension == "policy"
        assert report.sentiment_validation.dimension == "sentiment"

    def test_validate_all_strong_is_pass(self, agent):
        candidate = CandidateDirection(
            name="强方向",
            category="热点追逐",
            confidence=8.0,
            raw_metrics={"order_flow_profile": 2e9, "policy_level": "中央", "news_heat": 6, "limit_up_count": 5, "beneficiary_industries": ["电池"], "policy_time_window": "immediate"},
        )
        context = DirectionContext(date="2026-06-04")
        report = agent.validate(candidate, context)

        assert report.overall_status == "PASS"

    def test_validate_two_weak_is_reject(self, agent):
        candidate = CandidateDirection(
            name="弱方向",
            category="价值蓄势",
            confidence=5.0,
            raw_metrics={"order_flow_profile": -1e9, "policy_level": "地方", "news_heat": 2},
        )
        context = DirectionContext(date="2026-06-04")
        report = agent.validate(candidate, context)

        assert report.overall_status == "REJECT"

