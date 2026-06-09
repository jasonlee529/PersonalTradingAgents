import pytest

from src.agents.sector_discovery.validator.policy_validator import PolicyValidator
from src.agents.sector_discovery.models import CandidateDirection


class TestPolicyValidator:
    @pytest.fixture
    def validator(self):
        return PolicyValidator()

    def test_central_level_policy(self, validator):
        candidate = CandidateDirection(
            name="固态电池政策",
            category="政策前瞻",
            confidence=7.0,
            raw_metrics={"policy_level": "中央", "beneficiary_industries": ["电池", "材料"], "policy_time_window": "immediate"},
        )
        result = validator.validate(candidate)
        assert result.dimension == "policy"
        assert result.status == "strong"
        assert result.score >= 7

    def test_local_level_policy(self, validator):
        candidate = CandidateDirection(
            name="地方政策",
            category="政策前瞻",
            confidence=5.0,
            raw_metrics={"policy_level": "地方"},
        )
        result = validator.validate(candidate)
        assert result.dimension == "policy"

    def test_missing_policy_data(self, validator):
        candidate = CandidateDirection(
            name="无政策",
            category="热点追逐",
            confidence=5.0,
            raw_metrics={},
        )
        result = validator.validate(candidate)
        assert result.status == "missing"
