from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.agents.sector_discovery.llm_utils import llm_catalyst_analysis
from src.agents.sector_discovery.models import (
    CatalystEvent,
    CatalystTimeline,
    DirectionContext,
    SelectedDirection,
)
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


class CatalystAgent:
    """Builds catalyst timeline for a direction."""

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
    ) -> CatalystTimeline:
        """Build catalyst timeline for a direction."""
        if self.settings.sector_discovery_mock_mode:
            return self._analyze_mock(direction, context.date)

        # Live LLM mode
        llm_result = await llm_catalyst_analysis(direction.name, context.date, self.settings)
        if llm_result is None:
            logger.warning("Catalyst LLM failed for %s, falling back to mock", direction.name)
            return self._analyze_mock(direction, context.date)

        events = [
            CatalystEvent(
                event_name=e.event_name,
                expected_date=e.expected_date,
                time_category=e.time_category,
                market_priced_in=e.market_priced_in,
                impact_assessment=e.impact_assessment,
                data_to_watch=e.data_to_watch,
            )
            for e in llm_result.events
        ]

        return CatalystTimeline(
            direction_name=direction.name,
            events=events,
            next_key_event=llm_result.next_key_event,
            recommended_action=llm_result.recommended_action,
        )

    def _analyze_mock(self, direction: SelectedDirection, base_date: str) -> CatalystTimeline:
        """Hard-coded template for mock / test mode."""
        events = self._generate_events(direction, base_date)

        events.sort(key=lambda e: e.expected_date or "")

        next_event = ""
        for event in events:
            if event.time_category in ["imminent", "expected"]:
                next_event = event.event_name
                break

        return CatalystTimeline(
            direction_name=direction.name,
            events=events,
            next_key_event=next_event,
            recommended_action=self._build_recommendation(events),
        )

    def _generate_events(
        self,
        direction: SelectedDirection,
        base_date: str,
    ) -> list[CatalystEvent]:
        events = []
        base = datetime.strptime(base_date, "%Y-%m-%d")

        events.append(CatalystEvent(
            event_name="政策发布/市场启动",
            expected_date=(base - timedelta(days=3)).strftime("%Y-%m-%d"),
            time_category="past",
            market_priced_in=7.0,
            impact_assessment="市场已大部分反应",
            data_to_watch="后续配套政策",
        ))

        events.append(CatalystEvent(
            event_name=f"{direction.name}行业峰会",
            expected_date=(base + timedelta(days=5)).strftime("%Y-%m-%d"),
            time_category="imminent",
            market_priced_in=3.0,
            impact_assessment="技术路线或订单可能超预期",
            data_to_watch="参会企业名单、技术路线表态",
        ))

        events.append(CatalystEvent(
            event_name="月度产销数据发布",
            expected_date=(base + timedelta(days=15)).strftime("%Y-%m-%d"),
            time_category="expected",
            market_priced_in=5.0,
            impact_assessment="验证需求景气度",
            data_to_watch="环比增速、市占率变化",
        ))

        events.append(CatalystEvent(
            event_name="季度财报季",
            expected_date=(base + timedelta(days=60)).strftime("%Y-%m-%d"),
            time_category="long_term",
            market_priced_in=2.0,
            impact_assessment="业绩兑现验证",
            data_to_watch="毛利率、订单增速、产能利用率",
        ))

        if "政策" in direction.name or direction.name.endswith("政策受益"):
            events.append(CatalystEvent(
                event_name="部委细则出台",
                expected_date=(base + timedelta(days=10)).strftime("%Y-%m-%d"),
                time_category="expected",
                market_priced_in=2.0,
                impact_assessment="政策细节可能超预期",
                data_to_watch="补贴力度、准入标准",
            ))

        return events

    def _build_recommendation(self, events: list[CatalystEvent]) -> str:
        imminent = [e for e in events if e.time_category == "imminent"]
        if imminent:
            return f"重点关注即将发生的: {imminent[0].event_name}"
        return "持续跟踪行业数据和政策动态"
