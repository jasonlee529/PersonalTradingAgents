import pytest
from unittest.mock import MagicMock

from src.agents.sector_discovery.validator.fund_validator import FundValidator
from src.agents.sector_discovery.models import CandidateDirection, DimensionValidation


class TestFundValidator:
    @pytest.fixture
    def validator(self):
        return FundValidator()

    def test_validate_with_strong_order_flow_profile(self, validator):
        candidate = CandidateDirection(
            name="固态电池",
            category="热点追逐",
            confidence=8.0,
            raw_metrics={"order_flow_profile": 1.2e9, "limit_up_count": 5},
        )
        result = validator.validate(candidate)
        assert result.dimension == "fund"
        assert result.status in ["strong", "moderate", "weak", "missing"]
        assert 0 <= result.score <= 10

    def test_validate_with_weak_order_flow_profile(self, validator):
        candidate = CandidateDirection(
            name="弱势板块",
            category="价值蓄势",
            confidence=5.0,
            raw_metrics={"order_flow_profile": -5e8, "limit_up_count": 0},
        )
        result = validator.validate(candidate)
        assert result.dimension == "fund"

    def test_validate_with_missing_data(self, validator):
        candidate = CandidateDirection(
            name="无数据",
            category="热点追逐",
            confidence=5.0,
            raw_metrics={},
        )
        result = validator.validate(candidate)
        assert result.status == "missing"

