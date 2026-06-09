"""Fallback behavior tests for Coordinator multi-agent pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.sector_discovery.llm_utils import SectorDiscoveryLLMError
from src.agents.sector_discovery.models import (
    CandidateDirection,
    ChainAnalysisReport,
    CatalystTimeline,
    DeepAnalysis,
    DimensionValidation,
    DirectionContext,
    DirectionReport,
    RiskAssessment,
    SelectedDirection,
    ValidationReport,
)


class TestFallbacks:
    @pytest.fixture
    def coordinator(self):
        settings = MagicMock()
        settings.feature_flags = {}
        cache = MagicMock()
        collector = MagicMock()
        from src.agents.sector_discovery.coordinator import Coordinator
        return Coordinator(settings, cache, collector)

    @pytest.mark.asyncio
    async def test_scout_timeout_returns_empty_report(self, coordinator):
        """When scout.scan() raises TimeoutError, return empty fallback report."""
        with patch.object(coordinator.scout, "scan", side_effect=asyncio.TimeoutError):
            context = DirectionContext(date="2026-06-04")
            report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert report.sectors == []
        assert "方向分析未能完成" in report.summary

    @pytest.mark.asyncio
    async def test_scout_exception_returns_empty_report(self, coordinator):
        """When scout.scan() raises generic Exception, return empty fallback report."""
        with patch.object(coordinator.scout, "scan", side_effect=Exception("scout crash")):
            context = DirectionContext(date="2026-06-04")
            report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert report.sectors == []
        assert "方向分析未能完成" in report.summary

    @pytest.mark.asyncio
    async def test_validator_timeout_marks_flag(self, coordinator):
        """When validator.validate() raises TimeoutError, candidate gets FLAG report."""
        candidate = CandidateDirection(name="测试", category="热点", confidence=5.0)
        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate])):
            with patch.object(coordinator.validator, "validate", side_effect=asyncio.TimeoutError):
                with patch.object(coordinator.chain_analyst, "analyze", new=AsyncMock(
                    return_value=ChainAnalysisReport(direction_name="", segments=[])
                )):
                    with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                        return_value=CatalystTimeline(direction_name="", events=[])
                    )):
                        with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                            return_value=RiskAssessment(direction_name="")
                        )):
                            context = DirectionContext(date="2026-06-04")
                            report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert len(report.sectors) == 1
        assert report.sectors[0].name == "测试"
        # FLAG report should use candidate confidence as fallback score
        assert report.sectors[0].fund_score == 5.0
        assert report.sectors[0].policy_score == 5.0

    @pytest.mark.asyncio
    async def test_validator_exception_marks_flag(self, coordinator):
        """When validator.validate() raises Exception, candidate gets FLAG report."""
        candidate = CandidateDirection(name="测试", category="热点", confidence=5.0)
        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate])):
            with patch.object(coordinator.validator, "validate", side_effect=Exception("timeout")):
                with patch.object(coordinator.chain_analyst, "analyze", new=AsyncMock(
                    return_value=ChainAnalysisReport(direction_name="", segments=[])
                )):
                    with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                        return_value=CatalystTimeline(direction_name="", events=[])
                    )):
                        with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                            return_value=RiskAssessment(direction_name="")
                        )):
                            context = DirectionContext(date="2026-06-04")
                            report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert len(report.sectors) == 1
        assert report.sectors[0].name == "测试"
        # FLAG report should use candidate confidence as fallback score
        assert report.sectors[0].fund_score == 5.0
        assert report.sectors[0].policy_score == 5.0

    @pytest.mark.asyncio
    async def test_validator_failure_does_not_crash_pipeline(self, coordinator):
        """One candidate failing validation should not crash pipeline for others."""
        good = CandidateDirection(name="好方向", category="热点", confidence=8.0)
        bad = CandidateDirection(name="坏方向", category="热点", confidence=5.0)

        good_report = ValidationReport(
            direction_name="好方向",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=8.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=8.0),
            score_after_validation=8.0,
        )

        def validate_side_effect(candidate, context):
            if candidate.name == "坏方向":
                raise Exception("fail")
            return good_report

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[good, bad])):
            with patch.object(coordinator.validator, "validate", side_effect=validate_side_effect):
                with patch.object(coordinator.comparator, "compare", return_value=[]):
                    context = DirectionContext(date="2026-06-04")
                    report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert len(context.execution_log) >= 2

    @pytest.mark.asyncio
    async def test_all_rejected_returns_no_recommendation_report(self, coordinator):
        """When validation rejects every candidate, return a normal empty report."""
        candidate = CandidateDirection(name="policy-only", category="policy", confidence=7.0)
        rejected_report = ValidationReport(
            direction_name="policy-only",
            overall_status="REJECT",
            fund_validation=DimensionValidation(dimension="fund", status="missing", score=0.0),
            policy_validation=DimensionValidation(dimension="policy", status="weak", score=3.5),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="weak", score=0.0),
            score_after_validation=3.5,
        )

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate])):
            with patch.object(coordinator.validator, "validate", return_value=rejected_report):
                context = DirectionContext(date="2026-06-05")
                report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert report.sectors == []
        assert "[Fallback]" not in report.summary
        assert "\u4eca\u65e5\u6682\u65e0\u63a8\u8350\u65b9\u5411" in report.summary
        assert "1/1" in report.summary

    @pytest.mark.asyncio
    async def test_comparator_failure_fallback(self, coordinator):
        """When comparator.compare() fails, fallback to sorting by validation score."""
        candidate1 = CandidateDirection(name="高分", category="热点", confidence=9.0)
        candidate2 = CandidateDirection(name="低分", category="热点", confidence=5.0)

        report1 = ValidationReport(
            direction_name="高分",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=9.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=9.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=9.0),
            score_after_validation=9.0,
        )
        report2 = ValidationReport(
            direction_name="低分",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="moderate", score=5.0),
            policy_validation=DimensionValidation(dimension="policy", status="moderate", score=5.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="moderate", score=5.0),
            score_after_validation=5.0,
        )

        def validate_side_effect(candidate, context):
            return report1 if candidate.name == "高分" else report2

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate1, candidate2])):
            with patch.object(coordinator.validator, "validate", side_effect=validate_side_effect):
                with patch.object(coordinator.comparator, "compare", side_effect=Exception("comparator crash")):
                    with patch.object(coordinator.chain_analyst, "analyze", new=AsyncMock(
                        return_value=ChainAnalysisReport(direction_name="", segments=[])
                    )):
                        with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                            return_value=CatalystTimeline(direction_name="", events=[])
                        )):
                            with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                                return_value=RiskAssessment(direction_name="")
                            )):
                                context = DirectionContext(date="2026-06-04")
                                report = await coordinator.run(context)

        assert isinstance(report, DirectionReport)
        assert len(report.sectors) == 2
        assert report.sectors[0].name == "高分"
        assert report.sectors[1].name == "低分"

    @pytest.mark.asyncio
    async def test_comparator_timeout_fallback(self, coordinator):
        """When comparator.compare() times out, fallback to sorting by validation score."""
        candidate = CandidateDirection(name="测试", category="热点", confidence=8.0)
        report = ValidationReport(
            direction_name="测试",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=8.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=8.0),
            score_after_validation=8.0,
        )

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate])):
            with patch.object(coordinator.validator, "validate", return_value=report):
                with patch.object(coordinator.comparator, "compare", side_effect=asyncio.TimeoutError):
                    with patch.object(coordinator.chain_analyst, "analyze", new=AsyncMock(
                        return_value=ChainAnalysisReport(direction_name="", segments=[])
                    )):
                        with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                            return_value=CatalystTimeline(direction_name="", events=[])
                        )):
                            with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                                return_value=RiskAssessment(direction_name="")
                            )):
                                context = DirectionContext(date="2026-06-04")
                                result = await coordinator.run(context)

        assert isinstance(result, DirectionReport)
        assert len(result.sectors) == 1
        assert result.sectors[0].name == "测试"

    @pytest.mark.asyncio
    async def test_deep_dive_partial_failure_continues(self, coordinator):
        """One deep dive agent failing should not affect others or other directions."""
        candidate = CandidateDirection(name="测试", category="热点", confidence=8.0)
        report = ValidationReport(
            direction_name="测试",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=8.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=8.0),
            score_after_validation=8.0,
        )
        selected = SelectedDirection(name="测试", rank=1, total_score=8.0)

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate])):
            with patch.object(coordinator.validator, "validate", return_value=report):
                with patch.object(coordinator.comparator, "compare", return_value=[selected]):
                    with patch.object(coordinator.chain_analyst, "analyze", side_effect=Exception("fail")):
                        with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                            return_value=CatalystTimeline(direction_name="测试", events=[])
                        )):
                            with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                                return_value=RiskAssessment(direction_name="测试")
                            )):
                                context = DirectionContext(date="2026-06-04")
                                result = await coordinator.run(context)

        assert isinstance(result, DirectionReport)
        assert len(result.sectors) == 1

        deep = context.deep_analysis.get("测试")
        assert deep is not None
        assert deep.chain is None
        assert deep.catalyst is not None
        assert deep.risk is not None

    @pytest.mark.asyncio
    async def test_deep_dive_live_llm_parse_failure_continues(self, coordinator):
        """Live-mode structured-output failures should degrade the sub-analysis only."""
        coordinator.settings.sector_discovery_mock_mode = False
        candidate = CandidateDirection(name="AI算力", category="热点", confidence=8.0)
        report = ValidationReport(
            direction_name="AI算力",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=8.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=8.0),
            score_after_validation=8.0,
        )
        selected = SelectedDirection(name="AI算力", rank=1, total_score=8.0)

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate])):
            with patch.object(coordinator.validator, "validate", return_value=report):
                with patch.object(coordinator.comparator, "compare", return_value=[selected]):
                    with patch.object(
                        coordinator.chain_analyst,
                        "analyze",
                        new=AsyncMock(side_effect=SectorDiscoveryLLMError("parsed=None")),
                    ):
                        with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                            return_value=CatalystTimeline(direction_name="AI算力", events=[])
                        )):
                            with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                                return_value=RiskAssessment(direction_name="AI算力")
                            )):
                                context = DirectionContext(date="2026-06-04")
                                result = await coordinator.run(context)

        assert isinstance(result, DirectionReport)
        assert len(result.sectors) == 1

        deep = context.deep_analysis.get("AI算力")
        assert deep is not None
        assert deep.chain is None
        assert deep.catalyst is not None
        assert deep.risk is not None
        assert any(
            record.phase == "deep_dive" and record.status == "fallback"
            for record in context.execution_log
        )

    @pytest.mark.asyncio
    async def test_deep_dive_multiple_directions_one_fails(self, coordinator):
        """Deep dive failure in one direction should not affect other directions."""
        candidate1 = CandidateDirection(name="方向A", category="热点", confidence=8.0)
        candidate2 = CandidateDirection(name="方向B", category="热点", confidence=7.0)

        report1 = ValidationReport(
            direction_name="方向A",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=8.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=8.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=8.0),
            score_after_validation=8.0,
        )
        report2 = ValidationReport(
            direction_name="方向B",
            overall_status="PASS",
            fund_validation=DimensionValidation(dimension="fund", status="strong", score=7.0),
            policy_validation=DimensionValidation(dimension="policy", status="strong", score=7.0),
            sentiment_validation=DimensionValidation(dimension="sentiment", status="strong", score=7.0),
            score_after_validation=7.0,
        )

        selected1 = SelectedDirection(name="方向A", rank=1, total_score=8.0)
        selected2 = SelectedDirection(name="方向B", rank=2, total_score=7.0)

        def validate_side_effect(candidate, context):
            return report1 if candidate.name == "方向A" else report2

        async def chain_side_effect(direction, context):
            if direction.name == "方向A":
                raise Exception("chain fail")
            return ChainAnalysisReport(direction_name=direction.name, segments=[])

        with patch.object(coordinator.scout, "scan", new=AsyncMock(return_value=[candidate1, candidate2])):
            with patch.object(coordinator.validator, "validate", side_effect=validate_side_effect):
                with patch.object(coordinator.comparator, "compare", return_value=[selected1, selected2]):
                    with patch.object(coordinator.chain_analyst, "analyze", side_effect=chain_side_effect):
                        with patch.object(coordinator.catalyst_agent, "analyze", new=AsyncMock(
                            return_value=CatalystTimeline(direction_name="", events=[])
                        )):
                            with patch.object(coordinator.risk_agent, "analyze", new=AsyncMock(
                                return_value=RiskAssessment(direction_name="")
                            )):
                                context = DirectionContext(date="2026-06-04")
                                result = await coordinator.run(context)

        assert isinstance(result, DirectionReport)
        assert len(result.sectors) == 2

        deep_a = context.deep_analysis.get("方向A")
        deep_b = context.deep_analysis.get("方向B")
        assert deep_a is not None
        assert deep_a.chain is None
        assert deep_a.catalyst is not None
        assert deep_a.risk is not None
        assert deep_b is not None
        assert deep_b.chain is not None
        assert deep_b.catalyst is not None
        assert deep_b.risk is not None
