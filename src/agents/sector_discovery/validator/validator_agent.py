from __future__ import annotations

import logging

from src.agents.sector_discovery.models import (
    CandidateDirection,
    DirectionContext,
    ValidationReport,
)
from src.agents.sector_discovery.validator.fund_validator import FundValidator
from src.agents.sector_discovery.validator.policy_validator import PolicyValidator
from src.agents.sector_discovery.validator.sentiment_validator import SentimentValidator
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


class ValidatorAgent:
    """Runs three-dimension validation on a candidate direction."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        collector: DataCollector,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = collector
        self.fund_validator = FundValidator()
        self.policy_validator = PolicyValidator()
        self.sentiment_validator = SentimentValidator()

    def validate(
        self,
        candidate: CandidateDirection,
        context: DirectionContext,
    ) -> ValidationReport:
        """Validate a candidate direction across three dimensions."""
        fund_val = self.fund_validator.validate(candidate)
        policy_val = self.policy_validator.validate(candidate)
        sentiment_val = self.sentiment_validator.validate(candidate)

        statuses = [fund_val.status, policy_val.status, sentiment_val.status]
        strong_count = statuses.count("strong")
        moderate_count = statuses.count("moderate")
        weak_count = statuses.count("weak")
        missing_count = statuses.count("missing")

        # Scoring logic: data-present dimensions count more than missing
        present_count = strong_count + moderate_count + weak_count

        if strong_count >= 2 and weak_count == 0:
            overall = "PASS"
        elif strong_count == 1 and moderate_count >= 1 and weak_count == 0:
            overall = "PASS"
        elif weak_count >= 2 and present_count >= 2:
            # Only REJECT when we have actual data showing weakness
            overall = "REJECT"
        elif weak_count >= 1 and present_count >= 2:
            overall = "FLAG"
        else:
            # Mostly missing data — not enough to reject, flag for review
            overall = "FLAG"

        valid_scores = [
            fund_val.score if fund_val.status != "missing" else 0,
            policy_val.score if policy_val.status != "missing" else 0,
            sentiment_val.score if sentiment_val.status != "missing" else 0,
        ]
        non_missing = [s for s in valid_scores if s > 0]
        composite = sum(non_missing) / len(non_missing) if non_missing else 0.0

        rejection_reason = ""
        if overall == "REJECT":
            reasons = []
            if fund_val.status in ["weak", "missing"]:
                reasons.append("资金验证不通过")
            if policy_val.status in ["weak", "missing"]:
                reasons.append("政策验证不通过")
            if sentiment_val.status in ["weak", "missing"]:
                reasons.append("情绪验证不通过")
            rejection_reason = "；".join(reasons)

        watch_points = []
        watch_points.extend(fund_val.concerns)
        watch_points.extend(policy_val.concerns)
        watch_points.extend(sentiment_val.concerns)

        return ValidationReport(
            direction_name=candidate.name,
            overall_status=overall,
            fund_validation=fund_val,
            policy_validation=policy_val,
            sentiment_validation=sentiment_val,
            score_after_validation=composite,
            rejection_reason=rejection_reason,
            watch_points=watch_points,
        )
