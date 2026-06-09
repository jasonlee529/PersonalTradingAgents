from __future__ import annotations

import logging

from src.agents.sector_discovery.llm_utils import llm_risk_analysis
from src.agents.sector_discovery.models import (
    DirectionContext,
    RiskAssessment,
    RiskTrigger,
    SelectedDirection,
)
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


class RiskAgent:
    """Identifies risks and invalidation conditions for a direction."""

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
    ) -> RiskAssessment:
        if self.settings.sector_discovery_mock_mode:
            return self._analyze_mock(direction, context)

        # Live LLM mode
        llm_result = await llm_risk_analysis(direction.name, self.settings)
        if llm_result is None:
            logger.warning("Risk LLM failed for %s, falling back to mock", direction.name)
            return self._analyze_mock(direction, context)

        return RiskAssessment(
            direction_name=direction.name,
            overall_risk_level=llm_result.overall_risk_level,
            market_risks=[
                RiskTrigger(
                    condition=r.condition,
                    metric_name=r.metric_name,
                    threshold=r.threshold,
                    severity=r.severity,
                )
                for r in llm_result.market_risks
            ],
            policy_risks=[
                RiskTrigger(
                    condition=r.condition,
                    metric_name=r.metric_name,
                    threshold=r.threshold,
                    severity=r.severity,
                )
                for r in llm_result.policy_risks
            ],
            fundamental_risks=[
                RiskTrigger(
                    condition=r.condition,
                    metric_name=r.metric_name,
                    threshold=r.threshold,
                    severity=r.severity,
                )
                for r in llm_result.fundamental_risks
            ],
            invalidation_conditions=llm_result.invalidation_conditions,
            alternative_directions=llm_result.alternative_directions,
        )

    def _analyze_mock(
        self,
        direction: SelectedDirection,
        context: DirectionContext,
    ) -> RiskAssessment:
        """Hard-coded template for mock / test mode."""
        validation = None
        for report in context.validation_results:
            if report.direction_name == direction.name:
                validation = report
                break

        market_risks = self._build_market_risks(direction, validation)
        policy_risks = self._build_policy_risks(direction, validation)
        fundamental_risks = self._build_fundamental_risks(direction)

        invalidation = self._build_invalidation_conditions(direction)
        alternatives = self._suggest_alternatives(direction)

        risk_level = self._calculate_risk_level(
            market_risks, policy_risks, fundamental_risks, validation
        )

        return RiskAssessment(
            direction_name=direction.name,
            overall_risk_level=risk_level,
            market_risks=market_risks,
            policy_risks=policy_risks,
            fundamental_risks=fundamental_risks,
            invalidation_conditions=invalidation,
            alternative_directions=alternatives,
        )

    def _build_market_risks(self, direction, validation) -> list[RiskTrigger]:
        risks = []
        risks.append(RiskTrigger(
            condition="板块成交额连续3日萎缩30%",
            metric_name="板块成交额",
            threshold="连续3日萎缩30%",
            severity="warning",
        ))
        risks.append(RiskTrigger(
            condition="龙头股价跌破20日线且放量下跌",
            metric_name="龙头股价格",
            threshold="跌破20日线",
            severity="critical",
        ))
        if validation and validation.sentiment_validation.concerns:
            risks.append(RiskTrigger(
                condition="舆情热度骤降或出现重大负面",
                metric_name="舆情热度",
                threshold="热度排名跌出前20",
                severity="warning",
            ))
        return risks

    def _build_policy_risks(self, direction, validation) -> list[RiskTrigger]:
        risks = []
        if direction.name.endswith("政策受益") or "政策" in direction.name:
            risks.append(RiskTrigger(
                condition="政策细则弱于预期或延迟出台",
                metric_name="政策出台进度",
                threshold="预期时间窗口后2周仍未出台",
                severity="critical",
            ))
        risks.append(RiskTrigger(
            condition="监管表态转向收紧",
            metric_name="监管动态",
            threshold="出现限制性表述",
            severity="critical",
        ))
        return risks

    def _build_fundamental_risks(self, direction) -> list[RiskTrigger]:
        risks = []
        risks.append(RiskTrigger(
            condition="核心企业订单环比下滑",
            metric_name="订单数据",
            threshold="连续2个月环比负增长",
            severity="warning",
        ))
        risks.append(RiskTrigger(
            condition="上游原材料价格暴涨挤压利润",
            metric_name="原材料价格",
            threshold="单月涨幅超20%",
            severity="warning",
        ))
        return risks

    def _build_invalidation_conditions(self, direction) -> list[str]:
        conditions = [
            "龙头股价跌破20日线且放量下跌",
            "板块成交额连续5日萎缩",
        ]
        if "政策" in direction.name:
            conditions.append("政策落地严重不及预期")
        if getattr(direction, "category", "") == "热点追逐":
            conditions.append("涨停家数连续3日为0且资金净流出")
        return conditions

    def _suggest_alternatives(self, direction) -> list[str]:
        alternatives_map = {
            "固态电池": ["钠离子电池", "传统锂电材料"],
            "半导体": ["半导体设备", "Chiplet封装"],
            "商业航天": ["低空经济", "卫星互联网"],
            "AI": ["算力", "光模块"],
        }
        for key, alts in alternatives_map.items():
            if key in direction.name:
                return alts
        return ["同产业链其他细分环节"]

    def _calculate_risk_level(self, market_risks, policy_risks, fundamental_risks, validation) -> str:
        critical_count = sum(
            1 for r in market_risks + policy_risks + fundamental_risks
            if r.severity == "critical"
        )
        total = len(market_risks) + len(policy_risks) + len(fundamental_risks)

        if critical_count >= 2:
            return "high"
        elif critical_count >= 1 or total >= 5:
            return "moderate"
        return "low"
