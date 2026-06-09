import pytest

from src.agents.sector_discovery.models import (
    DirectionContext,
    CandidateDirection,
    SignalEvidence,
    ValidationReport,
    DimensionValidation,
    SelectedDirection,
    ChainSegmentAnalysis,
    ChainAnalysisReport,
    CatalystEvent,
    CatalystTimeline,
    RiskTrigger,
    RiskAssessment,
    DeepAnalysis,
    DirectionReport,
    SectorSnapshot,
)


class TestDirectionContext:
    def test_default_initialization(self):
        ctx = DirectionContext(date="2026-06-04")
        assert ctx.date == "2026-06-04"
        assert ctx.candidate_directions == []
        assert ctx.validation_results == []
        assert ctx.selected_directions == []
        assert ctx.deep_analysis == {}

    def test_with_candidates(self):
        candidate = CandidateDirection(
            name="固态电池",
            category="热点追逐",
            confidence=8.5,
            evidence_signals=[],
            raw_metrics={},
        )
        ctx = DirectionContext(
            date="2026-06-04",
            candidate_directions=[candidate],
        )
        assert len(ctx.candidate_directions) == 1
        assert ctx.candidate_directions[0].name == "固态电池"


class TestDirectionReport:
    def test_to_markdown_does_not_prepend_sector_score_list(self):
        report = DirectionReport(
            date="2026-06-05",
            sectors=[
                SectorSnapshot(
                    board_code="",
                    name="机器人",
                    tags=["热点追逐"],
                    composite_score=1.2,
                )
            ],
            summary="### 一、市场总览\n\n正文",
        )

        md = report.to_markdown()

        assert md.startswith("# 2026-06-05 今日方向")
        assert "【热点追逐】机器人" not in md
        assert "方向强度 1.2/10" not in md
        assert "### 一、市场总览" in md


class TestCandidateDirection:
    def test_creation(self):
        signal = SignalEvidence(
            source="market_heat",
            description="5股涨停",
            strength=8.0,
            data_snapshot={"limit_up_count": 5},
        )
        cand = CandidateDirection(
            name="固态电池",
            category="热点追逐",
            confidence=8.5,
            evidence_signals=[signal],
            raw_metrics={"order_flow_profile": 1.2e9},
        )
        assert cand.name == "固态电池"
        assert cand.confidence == 8.5
        assert len(cand.evidence_signals) == 1
        assert cand.evidence_signals[0].source == "market_heat"


class TestValidationReport:
    def test_pass_status(self):
        fund = DimensionValidation(
            dimension="fund",
            status="strong",
            score=8.5,
            evidence="主力净流入12亿",
        )
        policy = DimensionValidation(
            dimension="policy",
            status="strong",
            score=9.0,
            evidence="中央级政策",
        )
        sentiment = DimensionValidation(
            dimension="sentiment",
            status="moderate",
            score=6.5,
            evidence="舆情热度偏高",
        )
        report = ValidationReport(
            direction_name="固态电池",
            overall_status="PASS",
            fund_validation=fund,
            policy_validation=policy,
            sentiment_validation=sentiment,
            score_after_validation=8.0,
        )
        assert report.overall_status == "PASS"
        assert report.fund_validation.status == "strong"


class TestSelectedDirection:
    def test_creation(self):
        sel = SelectedDirection(
            name="固态电池",
            rank=1,
            total_score=8.7,
            fund_score=8.5,
            policy_score=9.0,
            sentiment_score=6.5,
            chain_depth_score=8.0,
            catalyst_score=7.5,
            selection_reason="资金与政策双强",
            comparison_notes="优于低空经济",
        )
        assert sel.rank == 1
        assert sel.total_score == 8.7


class TestChainAnalysis:
    def test_segment(self):
        segment = ChainSegmentAnalysis(
            segment_name="铝塑膜",
            position="upstream",
            market_perception="普通包装材料",
            reality_assessment="技术壁垒高",
            expectation_gap=9.2,
            investment_logic="进口替代加速",
        )
        assert segment.expectation_gap == 9.2
        assert segment.position == "upstream"

    def test_report(self):
        segment = ChainSegmentAnalysis(
            segment_name="铝塑膜",
            position="upstream",
            expectation_gap=9.2,
        )
        report = ChainAnalysisReport(
            direction_name="固态电池",
            segments=[segment],
            top_segment="铝塑膜",
            diffusion_path="铝塑膜 → 电解质",
        )
        assert report.top_segment == "铝塑膜"


class TestCatalystTimeline:
    def test_event(self):
        event = CatalystEvent(
            event_name="行业峰会",
            expected_date="2026-06-10",
            time_category="imminent",
            market_priced_in=3.0,
            impact_assessment="技术路线表态",
        )
        assert event.time_category == "imminent"

    def test_timeline(self):
        event = CatalystEvent(
            event_name="行业峰会",
            time_category="imminent",
        )
        timeline = CatalystTimeline(
            direction_name="固态电池",
            events=[event],
            next_key_event="行业峰会",
        )
        assert timeline.next_key_event == "行业峰会"


class TestRiskAssessment:
    def test_trigger(self):
        trigger = RiskTrigger(
            condition="板块成交额连续3日萎缩30%",
            metric_name="板块成交额",
            threshold="连续3日萎缩30%",
            severity="warning",
        )
        assert trigger.severity == "warning"

    def test_assessment(self):
        risk = RiskAssessment(
            direction_name="固态电池",
            overall_risk_level="moderate",
            invalidation_conditions=["龙头跌破20日线"],
            alternative_directions=["钠离子电池"],
        )
        assert risk.overall_risk_level == "moderate"


class TestDeepAnalysis:
    def test_creation(self):
        deep = DeepAnalysis()
        assert deep.chain is None
        assert deep.catalyst is None
        assert deep.risk is None


