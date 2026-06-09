"""LLM utilities for Sector Discovery — async wrapper around the project's LLM client factory."""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from src.agents.tradingagents.llm_clients.factory import create_llm_client
from src.agents.tradingagents.llm_clients.provider_catalog import get_api_key_field
from src.config import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class SectorDiscoveryLLMError(RuntimeError):
    """Raised when live daily-direction LLM generation fails."""


# ── Chain Analysis ────────────────────────────────────────────────────────

SYSTEM_PROMPT_CHAIN = """你是 A 股产业链分析专家。

任务：给定一个市场热点概念/方向，深入分析其产业链上中下游各环节，找出"预期差"最大的环节。

输出必须是以下 JSON 格式，不要包含任何其他文本：
{
  "direction_name": "方向名称",
  "segments": [
    {
      "segment_name": "环节名称（如光刻胶、硅片、晶圆制造等）",
      "position": "位置（upstream/midstream/downstream/supporting之一）",
      "market_perception": "市场当前怎么看这个环节（共识）",
      "reality_assessment": "真实产业状况（事实）",
      "expectation_gap": 7.5,
      "key_players": ["A股代码+简称"],
      "price_trend": "近期价格/股价趋势",
      "capacity_utilization": "产能利用率状况",
      "order_backlog_trend": "订单/排产趋势",
      "investment_logic": "投资逻辑一句话总结",
      "time_horizon": "推荐持有周期（short/medium/long之一）"
    }
  ],
  "top_segment": "预期差最大的环节名",
  "diffusion_path": "热点如何沿产业链扩散（如上游材料 → 中游制造 → 下游应用）",
  "supporting_segments": ["配套/支撑环节名称列表"]
}

要求：
1. segments 至少包含 4-6 个环节
2. 按 expectation_gap 从高到低排序（0-10 评分，越高越好）
3. 用中文输出，数据尽量具体、有依据
4. 必须严格遵循上述 JSON 字段名，不要改字段名"""


class _ChainSegmentLLM(BaseModel):
    segment_name: str
    position: Literal["upstream", "midstream", "downstream", "supporting"]
    market_perception: str = ""
    reality_assessment: str = ""
    expectation_gap: float = Field(ge=0.0, le=10.0)
    key_players: list[str] = Field(default_factory=list)
    price_trend: str = ""
    capacity_utilization: str = ""
    order_backlog_trend: str = ""
    investment_logic: str = ""
    time_horizon: str = ""

    @field_validator("key_players", mode="before")
    @classmethod
    def _coerce_key_players(cls, value):
        if isinstance(value, str):
            return [
                item.strip()
                for item in value.replace("，", ",").replace("、", ",").split(",")
                if item.strip()
            ]
        return value


class _ChainAnalysisLLM(BaseModel):
    direction_name: str
    segments: list[_ChainSegmentLLM]
    top_segment: str
    diffusion_path: str
    supporting_segments: list[str] = Field(default_factory=list)


async def llm_chain_analysis(direction_name: str, settings: Settings):
    """Call LLM for supply-chain analysis. Returns _ChainAnalysisLLM or None."""
    prompt = (
        f"方向名称：{direction_name}\n"
        f"日期：{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}\n"
        "请对该方向的产业链进行深入分析，输出结构化结果。"
    )
    return await llm_structured_output(
        prompt, _ChainAnalysisLLM, settings, SYSTEM_PROMPT_CHAIN,
        llm_type="deep",
        test_mode=settings.sector_discovery_mock_mode,
    )


# ── Catalyst Timeline ─────────────────────────────────────────────────────

SYSTEM_PROMPT_CATALYST = """你是 A 股市场催化事件分析专家。

任务：给定一个市场投资方向，梳理未来可见的关键催化事件时间轴，并给出投资建议。

输出必须是以下 JSON 格式，不要包含任何其他文本：
{
  "direction_name": "方向名称",
  "events": [
    {
      "event_name": "事件名称",
      "expected_date": "2026-06-15",
      "time_category": "时间分类（past/imminent/expected/long_term之一）",
      "market_priced_in": 5.0,
      "impact_assessment": "影响评估（对股价的潜在影响方向和幅度）",
      "data_to_watch": "需要跟踪的关键数据/信号"
    }
  ],
  "next_key_event": "下一个最重要的催化事件名称",
  "recommended_action": "基于催化时间轴的推荐行动（如等待回调后建仓、事件前减仓等）"
}

要求：
1. events 至少包含 3-5 个事件
2. 事件尽量具体（如"某月某日发布月度数据"而非泛泛的"数据发布"）
3. 用中文输出
4. 必须严格遵循上述 JSON 字段名"""


class _CatalystEventLLM(BaseModel):
    event_name: str
    expected_date: str | None = None
    time_category: Literal["past", "imminent", "expected", "long_term"] = "expected"
    market_priced_in: float = Field(ge=0.0, le=10.0)
    impact_assessment: str = ""
    data_to_watch: str = ""


class _CatalystTimelineLLM(BaseModel):
    direction_name: str
    events: list[_CatalystEventLLM]
    next_key_event: str
    recommended_action: str


async def llm_catalyst_analysis(direction_name: str, base_date: str, settings: Settings):
    """Call LLM for catalyst timeline analysis. Returns _CatalystTimelineLLM or None."""
    prompt = (
        f"方向名称：{direction_name}\n"
        f"基准日期：{base_date}\n"
        "请梳理该方向的关键催化事件时间轴，输出结构化结果。"
    )
    return await llm_structured_output(
        prompt, _CatalystTimelineLLM, settings, SYSTEM_PROMPT_CATALYST,
        llm_type="deep",
        test_mode=settings.sector_discovery_mock_mode,
    )


# ── Risk Assessment ───────────────────────────────────────────────────────

SYSTEM_PROMPT_RISK = """你是 A 股市场风险评估专家。

任务：给定一个市场投资方向，全面评估其风险并给出失效条件和替代方向。

输出必须是以下 JSON 格式，不要包含任何其他文本：
{
  "direction_name": "方向名称",
  "overall_risk_level": "综合风险等级（low/moderate/high之一）",
  "market_risks": [
    {
      "condition": "风险触发条件描述",
      "metric_name": "监控指标名称",
      "threshold": "阈值",
      "severity": "严重程度（warning/critical之一）"
    }
  ],
  "policy_risks": [
    {
      "condition": "风险触发条件描述",
      "metric_name": "监控指标名称",
      "threshold": "阈值",
      "severity": "严重程度（warning/critical之一）"
    }
  ],
  "fundamental_risks": [
    {
      "condition": "风险触发条件描述",
      "metric_name": "监控指标名称",
      "threshold": "阈值",
      "severity": "严重程度（warning/critical之一）"
    }
  ],
  "invalidation_conditions": ["失效条件列表（一旦发生就说明方向逻辑被破坏，应止损）"],
  "alternative_directions": ["替代方向列表（如果本方向失效，可以考虑的替代投资方向）"]
}

要求：
1. 每个风险列表至少包含 2-3 项
2. 风险描述尽量量化、可操作
3. 用中文输出
4. 必须严格遵循上述 JSON 字段名"""


class _RiskTriggerLLM(BaseModel):
    condition: str
    metric_name: str = ""
    threshold: str = ""
    severity: Literal["warning", "critical"] = "warning"


class _RiskAssessmentLLM(BaseModel):
    direction_name: str
    overall_risk_level: Literal["low", "moderate", "high"] = "moderate"
    market_risks: list[_RiskTriggerLLM] = Field(default_factory=list)
    policy_risks: list[_RiskTriggerLLM] = Field(default_factory=list)
    fundamental_risks: list[_RiskTriggerLLM] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    alternative_directions: list[str] = Field(default_factory=list)


async def llm_risk_analysis(direction_name: str, settings: Settings):
    """Call LLM for risk assessment. Returns _RiskAssessmentLLM or None."""
    prompt = (
        f"方向名称：{direction_name}\n"
        f"日期：{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}\n"
        "请对该方向进行全面风险评估，输出结构化结果。"
    )
    return await llm_structured_output(
        prompt, _RiskAssessmentLLM, settings, SYSTEM_PROMPT_RISK,
        llm_type="deep",
        test_mode=settings.sector_discovery_mock_mode,
    )


# ── Generic helpers ───────────────────────────────────────────────────────

SYSTEM_PROMPT_CHAIN_REASONING = """你是 A 股产业链分析专家。

任务：给定一个市场热点概念和相关政策信号，深入分析其产业链上中下游各环节，找出"预期差"最大的环节。

分析原则：
1. 上游（材料/设备/零部件）通常预期差最大，因为市场关注度低、信息不对称
2. 中游（制造/集成）往往已有热度，估值偏高
3. 下游（应用/运营）业绩兑现周期长，纯概念风险高
4. 优先推荐：上游材料/设备 + 有订单/产能证据支撑 + 股价尚未反映

请用中文输出。"""


async def llm_chain_reasoning(
    prompt: str,
    settings: Settings,
    system_prompt: Optional[str] = None,
    llm_type: Literal["quick", "deep"] = "quick",
    test_mode: Optional[bool] = None,
) -> str:
    """Call LLM for supply-chain reasoning. Returns raw text response."""
    effective_test_mode = test_mode if test_mode is not None else settings.test_mode
    llm = _get_llm(settings, llm_type=llm_type, test_mode=test_mode)
    messages = [
        SystemMessage(content=system_prompt or SYSTEM_PROMPT_CHAIN_REASONING),
        HumanMessage(content=prompt),
    ]
    try:
        response = await llm.ainvoke(messages)
        return str(response.content)
    except Exception as e:
        logger.warning("LLM chain reasoning failed: %s", e)
        if not effective_test_mode:
            raise SectorDiscoveryLLMError(f"LLM chain reasoning failed: {e}") from e
        return ""


async def llm_structured_output(
    prompt: str,
    schema: type[T],
    settings: Settings,
    system_prompt: Optional[str] = None,
    llm_type: Literal["quick", "deep"] = "quick",
    test_mode: Optional[bool] = None,
) -> Optional[T]:
    """Call LLM with structured output (Pydantic schema)."""
    effective_test_mode = test_mode if test_mode is not None else settings.test_mode
    llm = _get_llm(settings, llm_type=llm_type, test_mode=test_mode)
    structured_llm = llm.with_structured_output(schema, include_raw=True)
    messages = [
        SystemMessage(content=system_prompt or SYSTEM_PROMPT_CHAIN_REASONING),
        HumanMessage(content=prompt),
    ]
    try:
        result = await structured_llm.ainvoke(messages)
        parsed = result.get("parsed")
        if parsed is None:
            raw = result.get("raw")
            raw_content = getattr(raw, "content", str(raw)) if raw else "N/A"
            repair_prompt = HumanMessage(
                content=(
                    "Your previous response could not be parsed. Return only a valid JSON "
                    f"object matching this Pydantic schema, with no markdown or extra text:\n"
                    f"{schema.model_json_schema()}\n\n"
                    f"Previous response:\n{raw_content[:2000]}"
                )
            )
            retry_result = await structured_llm.ainvoke([*messages, repair_prompt])
            parsed = retry_result.get("parsed")
            if parsed is not None:
                return parsed
            retry_raw = retry_result.get("raw")
            retry_content = getattr(retry_raw, "content", str(retry_raw)) if retry_raw else raw_content
            logger.warning(
                "LLM structured output parsed=None for %s | raw=%s",
                schema.__name__, retry_content[:500],
            )
            if not effective_test_mode:
                raise SectorDiscoveryLLMError(
                    f"LLM structured output parsed=None for {schema.__name__}"
                )
            return None
        return parsed
    except SectorDiscoveryLLMError:
        raise
    except Exception as e:
        logger.warning("LLM structured output failed for %s: %s", schema.__name__, e)
        if not effective_test_mode:
            raise SectorDiscoveryLLMError(
                f"LLM structured output failed for {schema.__name__}: {e}"
            ) from e
        return None


def _get_llm(
    settings: Settings,
    llm_type: Literal["quick", "deep"] = "deep",
    test_mode: Optional[bool] = None,
):
    """Create and return a LangChain chat model."""
    provider = _get_sector_provider(settings)
    # Ensure API key is in environment
    _inject_api_key(settings, provider)

    # sector_discovery uses its own mock_mode; fallback to global test_mode
    effective_test_mode = test_mode if test_mode is not None else settings.test_mode

    client = create_llm_client(
        provider=provider,
        model=settings.get_llm_model(provider, llm_type),
        test_mode=effective_test_mode,
    )
    return client.get_llm()


def _get_sector_provider(settings: Settings) -> str:
    return settings.daily_direction_llm_provider or "deepseek"


def _get_llm_api_key(settings: Settings, provider: str) -> str:
    key_field = get_api_key_field(provider)
    return getattr(settings, key_field, "") if key_field else ""


def _inject_api_key(settings: Settings, provider: str) -> None:
    """Inject the configured API key into the environment variable expected by the LLM client."""
    from src.agents.tradingagents.llm_clients.api_key_env import get_api_key_env

    api_key = _get_llm_api_key(settings, provider)
    env_var = get_api_key_env(provider)
    if env_var and api_key:
        os.environ[env_var] = api_key
