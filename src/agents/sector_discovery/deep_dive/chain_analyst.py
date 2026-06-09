from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.llm_utils import llm_chain_analysis
from src.agents.sector_discovery.models import (
    ChainAnalysisReport,
    ChainSegmentAnalysis,
    DirectionContext,
    SelectedDirection,
)
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


class ChainAnalyst:
    """Analyzes supply chain segments for a direction."""

    CHAIN_TEMPLATES = {
        "固态电池": [
            ("铝塑膜", "upstream", "技术壁垒高，进口替代空间大"),
            ("电解质", "upstream", "新型电解质订单增长"),
            ("正极材料", "upstream", "高镍化趋势"),
            ("负极材料", "upstream", "硅碳负极突破"),
            ("电池制造", "midstream", "产能利用率提升"),
            ("检测设备", "supporting", "良率检测需求增长"),
            ("新能源车", "downstream", "销量驱动需求"),
            ("储能系统", "downstream", "第二增长曲线"),
        ],
        "半导体": [
            ("光刻胶", "upstream", "国产替代关键材料"),
            ("硅片", "upstream", "大尺寸化趋势"),
            ("EDA软件", "supporting", "设计工具自主可控"),
            ("晶圆制造", "midstream", "先进制程突破"),
            ("封测", "midstream", "先进封装技术"),
            ("AI芯片", "downstream", "算力需求爆发"),
            ("汽车芯片", "downstream", "车载半导体增长"),
        ],
    }

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        collector: DataCollector,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = collector

    async def analyze(
        self,
        direction: SelectedDirection,
        context: DirectionContext,
    ) -> ChainAnalysisReport:
        """Analyze supply chain for a direction."""
        if self.settings.sector_discovery_mock_mode:
            return await self._analyze_mock(direction)

        # Live LLM mode
        llm_result = await llm_chain_analysis(direction.name, self.settings)
        if llm_result is None:
            logger.warning("Chain LLM failed for %s, falling back to mock", direction.name)
            return await self._analyze_mock(direction)

        segments = [
            ChainSegmentAnalysis(
                segment_name=s.segment_name,
                position=s.position,
                market_perception=s.market_perception,
                reality_assessment=s.reality_assessment,
                expectation_gap=s.expectation_gap,
                key_players=s.key_players,
                price_trend=s.price_trend,
                capacity_utilization=s.capacity_utilization,
                order_backlog_trend=s.order_backlog_trend,
                investment_logic=s.investment_logic,
                time_horizon=s.time_horizon,
            )
            for s in llm_result.segments
        ]

        return ChainAnalysisReport(
            direction_name=direction.name,
            segments=segments,
            top_segment=llm_result.top_segment,
            diffusion_path=llm_result.diffusion_path,
            supporting_segments=llm_result.supporting_segments,
        )

    async def _analyze_mock(self, direction: SelectedDirection) -> ChainAnalysisReport:
        """Hard-coded template for mock / test mode."""
        segments = self._build_segments(direction.name)

        for segment in segments:
            segment.expectation_gap = self._calculate_gap(segment, direction)

        segments.sort(key=lambda s: s.expectation_gap, reverse=True)

        top_segment = segments[0].segment_name if segments else ""
        diffusion_path = self._build_diffusion_path(segments)
        supporting = [s.segment_name for s in segments if s.position == "supporting"]

        return ChainAnalysisReport(
            direction_name=direction.name,
            segments=segments,
            top_segment=top_segment,
            diffusion_path=diffusion_path,
            supporting_segments=supporting,
        )

    def _build_segments(self, direction_name: str) -> list[ChainSegmentAnalysis]:
        template = self.CHAIN_TEMPLATES.get(direction_name, [])

        if not template:
            template = [
                ("原材料", "upstream", "上游原材料供应"),
                ("核心设备", "upstream", "关键设备制造"),
                ("零部件", "midstream", "核心零部件"),
                ("组装制造", "midstream", "中游组装"),
                ("终端应用", "downstream", "下游应用"),
                ("配套服务", "supporting", "配套支持服务"),
            ]

        segments = []
        for name, position, logic in template:
            segments.append(ChainSegmentAnalysis(
                segment_name=name,
                position=position,
                investment_logic=logic,
            ))
        return segments

    def _calculate_gap(
        self,
        segment: ChainSegmentAnalysis,
        direction: SelectedDirection,
    ) -> float:
        position_bonus = {
            "upstream": 2.0,
            "midstream": 0.5,
            "downstream": -0.5,
            "supporting": 1.0,
        }

        base = 5.0
        bonus = position_bonus.get(segment.position, 0)
        rank_bonus = max(0, (6 - direction.rank) * 0.3)
        name_hash = sum(ord(c) for c in segment.segment_name) % 5

        gap = base + bonus + rank_bonus + name_hash * 0.3
        return min(10.0, max(1.0, gap))

    def _build_diffusion_path(self, segments: list[ChainSegmentAnalysis]) -> str:
        sorted_by_gap = sorted(segments, key=lambda s: s.expectation_gap, reverse=True)
        top3 = [s.segment_name for s in sorted_by_gap[:3]]
        return " → ".join(top3)
