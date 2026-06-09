"""Tests for Coordinator — multi-agent direction analysis orchestrator."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.sector_discovery.models import (
    CandidateDirection,
    ChainAnalysisReport,
    CatalystTimeline,
    DeepAnalysis,
    DirectionContext,
    DirectionReport,
    RiskAssessment,
    SelectedDirection,
    ValidationReport,
)


class TestCoordinator:
    @pytest.fixture
    def mock_settings(self):
        return MagicMock()

    @pytest.fixture
    def mock_cache(self):
        return MagicMock()

    @pytest.fixture
    def mock_collector(self):
        return MagicMock()

    @pytest.fixture
    def coordinator(self, mock_settings, mock_cache, mock_collector):
        from src.agents.sector_discovery.coordinator import Coordinator
        return Coordinator(mock_settings, mock_cache, mock_collector)

    @pytest.fixture
    def sample_candidates(self):
        return [
            CandidateDirection(name="固态电池", category="热点追逐", confidence=8.5),
            CandidateDirection(name="半导体", category="产业链预期差", confidence=7.5),
            CandidateDirection(name="AI算力", category="热点追逐", confidence=9.0),
        ]

    @pytest.fixture
    def sample_validation_reports(self):
        from src.agents.sector_discovery.models import DimensionValidation
        return [
            ValidationReport(
                direction_name="固态电池",
                overall_status="PASS",
                fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.0),
                policy_validation=DimensionValidation(dimension="policy", status="strong", score=7.5),
                sentiment_validation=DimensionValidation(dimension="sentiment", status="moderate", score=6.0),
                score_after_validation=7.2,
            ),
            ValidationReport(
                direction_name="半导体",
                overall_status="PASS",
                fund_validation=DimensionValidation(dimension="fund", status="strong", score=7.0),
                policy_validation=DimensionValidation(dimension="policy", status="moderate", score=6.5),
                sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=8.0),
                score_after_validation=7.0,
            ),
            ValidationReport(
                direction_name="AI算力",
                overall_status="FLAG",
                fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.5),
                policy_validation=DimensionValidation(dimension="policy", status="weak", score=4.0),
                sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=9.0),
                score_after_validation=7.0,
            ),
        ]

    @pytest.fixture
    def sample_selected_directions(self):
        return [
            SelectedDirection(name="固态电池", rank=1, total_score=8.5),
            SelectedDirection(name="AI算力", rank=2, total_score=8.0),
        ]

    @pytest.mark.asyncio
    async def test_run_returns_direction_report(
        self,
        coordinator,
        sample_candidates,
        sample_validation_reports,
        sample_selected_directions,
    ):
        """coordinator.run() returns a DirectionReport."""
        with patch.object(
            coordinator.scout, "scan", new=AsyncMock(return_value=sample_candidates)
        ), patch.object(
            coordinator.validator, "validate", side_effect=lambda c, ctx: next(
                r for r in sample_validation_reports if r.direction_name == c.name
            )
        ), patch.object(
            coordinator.comparator, "compare", return_value=sample_selected_directions
        ), patch.object(
            coordinator.chain_analyst, "analyze", new=AsyncMock(
                return_value=ChainAnalysisReport(direction_name="", segments=[])
            )
        ), patch.object(
            coordinator.catalyst_agent, "analyze", new=AsyncMock(
                return_value=CatalystTimeline(direction_name="", events=[])
            )
        ), patch.object(
            coordinator.risk_agent, "analyze", new=AsyncMock(
                return_value=RiskAssessment(direction_name="")
            )
        ):
            context = DirectionContext(date="2026-06-04")
            report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert report.date == "2026-06-04"

    @pytest.mark.asyncio
    async def test_run_with_empty_candidates_returns_fallback(self, coordinator):
        """When scout returns empty, get fallback report."""
        with patch.object(
            coordinator.scout, "scan", new=AsyncMock(return_value=[])
        ):
            context = DirectionContext(date="2026-06-04")
            report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert report.date == "2026-06-04"
        assert len(report.sectors) == 0
        assert "fallback" in report.summary.lower() or "empty" in report.summary.lower() or "候选" in report.summary or "发现" in report.summary

    def test_directions_to_snapshots_preserves_candidate_metrics(self, coordinator):
        context = DirectionContext(
            date="2026-06-04",
            candidate_directions=[
                CandidateDirection(
                    name="AI算力",
                    category="热点追逐",
                    confidence=6.0,
                    raw_metrics={
                        "heat_level": 6.0,
                        "limit_up_count": 3,
                        "order_flow_profile": 8e8,
                    },
                )
            ],
        )
        selected = [SelectedDirection(name="AI算力", rank=1, total_score=6.0)]

        snapshots = coordinator._directions_to_snapshots(selected, context)

        assert snapshots[0].tags == ["热点追逐"]
        assert snapshots[0].raw_metrics["heat_level"] == 6.0
        assert snapshots[0].raw_metrics["limit_up_count"] == 3
        assert snapshots[0].raw_metrics["order_flow_profile"] == 8e8

    @pytest.mark.asyncio
    async def test_run_normalizes_weekend_date(self, coordinator):
        with patch.object(
            coordinator.scout, "scan", new=AsyncMock(return_value=[])
        ):
            context = DirectionContext(date="2026-06-06")
            report = await coordinator.run(context)

        assert report.date == "2026-06-05"
        assert context.date == "2026-06-05"


