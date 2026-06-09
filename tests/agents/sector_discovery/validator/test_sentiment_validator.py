import pytest

from src.agents.sector_discovery.validator.sentiment_validator import SentimentValidator
from src.agents.sector_discovery.models import CandidateDirection


class TestSentimentValidator:
    @pytest.fixture
    def validator(self):
        return SentimentValidator()

    def test_balanced_sentiment(self, validator):
        candidate = CandidateDirection(
            name="固态电池",
            category="热点追逐",
            confidence=7.0,
            raw_metrics={"news_heat": 6.0, "limit_up_count": 3},
        )
        result = validator.validate(candidate)
        assert result.dimension == "sentiment"
        assert result.status in ["strong", "moderate", "weak"]

    def test_overheated_sentiment(self, validator):
        candidate = CandidateDirection(
            name="过热概念",
            category="热点追逐",
            confidence=9.0,
            raw_metrics={"news_heat": 9.5, "limit_up_count": 10},
        )
        result = validator.validate(candidate)
        assert result.dimension == "sentiment"
        assert "过热" in result.evidence or len(result.concerns) > 0
