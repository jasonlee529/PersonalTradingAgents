"""Mock LLM client for test mode — returns canned responses without API calls."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

from .base_client import BaseLLMClient


class MockChatModel(Runnable):
    """Mock chat model that returns placeholder responses without calling any API.

    Compatible with LangChain's Runnable interface: supports ``invoke``,
    ``with_structured_output``, and ``bind_tools`` so agents and chains
    work unchanged in test mode.
    """

    def __init__(self, model_name: str = "mock"):
        self.model_name = model_name

    def invoke(self, input, config=None, **kwargs) -> AIMessage:
        return AIMessage(
            content="[TEST MODE] 模拟分析内容。这是一条测试生成的占位文本，"
            "用于在不消耗真实 LLM token 的情况下运行流程。"
        )

    def ainvoke(self, input, config=None, **kwargs):
        return self.invoke(input, config, **kwargs)

    def with_structured_output(self, schema, **kwargs):
        return MockStructuredModel(schema)

    def bind_tools(self, tools, **kwargs):
        return MockBoundModel(self)


class MockBoundModel(Runnable):
    """Returned by ``MockChatModel.bind_tools`` — still returns prose, no tool calls."""

    def __init__(self, mock_llm: MockChatModel):
        self._mock_llm = mock_llm

    def invoke(self, input, config=None, **kwargs) -> AIMessage:
        return AIMessage(
            content="[TEST MODE] 模拟工具分析内容。测试模式下不执行真实工具调用。",
            tool_calls=[],
        )

    def ainvoke(self, input, config=None, **kwargs):
        return self.invoke(input, config, **kwargs)


class MockStructuredModel:
    """Returned by ``MockChatModel.with_structured_output`` — returns mock pydantic instances."""

    def __init__(self, schema):
        self.schema = schema

    def invoke(self, input, config=None, **kwargs):
        schema_name = getattr(self.schema, "__name__", str(self.schema))
        return _build_mock_instance(self.schema, schema_name)

    async def ainvoke(self, input, config=None, **kwargs):
        return self.invoke(input, config, **kwargs)


def _build_mock_instance(schema, schema_name: str):
    """Build a mock pydantic instance for the given schema."""
    try:
        from tradingagents.agents.schemas import (
            PortfolioDecision,
            PortfolioRating,
            ResearchPlan,
            TraderAction,
            TraderProposal,
        )
    except Exception:
        PortfolioDecision = PortfolioRating = ResearchPlan = TraderAction = TraderProposal = None  # type: ignore[misc]

    if PortfolioDecision and schema_name == "ResearchPlan":
        return ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="[TEST MODE] 测试模式生成的研究理由。",
            strategic_actions="[TEST MODE] 测试模式生成的战略行动建议。",
        )
    if TraderProposal and schema_name == "TraderProposal":
        return TraderProposal(
            action=TraderAction.HOLD,
            reasoning="[TEST MODE] 测试模式生成的交易理由。",
        )
    if PortfolioDecision and schema_name == "PortfolioDecision":
        return PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="[TEST MODE] 测试模式生成的执行摘要。",
            investment_thesis="[TEST MODE] 测试模式生成的投资论点。",
        )

    # Sector Discovery schemas
    if schema_name == "_ChainAnalysisLLM":
        from pydantic import create_model
        from typing import List
        segment_schema = None
        for field_name, field_info in schema.model_fields.items():
            if field_name == "segments":
                segment_schema = field_info.annotation
                if hasattr(segment_schema, "__args__"):
                    segment_schema = segment_schema.__args__[0]
                break
        segment = _build_mock_instance(segment_schema, getattr(segment_schema, "__name__", "_ChainSegmentLLM")) if segment_schema else {}
        return schema(
            direction_name="[TEST MODE] 测试方向",
            segments=[segment] if segment else [],
            top_segment="[TEST MODE] 测试环节",
            diffusion_path="上游 → 中游 → 下游",
            supporting_segments=["配套支撑"],
        )
    if schema_name == "_CatalystTimelineLLM":
        return schema(
            direction_name="[TEST MODE] 测试方向",
            events=[],
            next_key_event="[TEST MODE] 测试事件",
            recommended_action="持续跟踪",
        )
    if schema_name == "_RiskAssessmentLLM":
        return schema(
            direction_name="[TEST MODE] 测试方向",
            overall_risk_level="moderate",
            market_risks=[],
            policy_risks=[],
            fundamental_risks=[],
            invalidation_conditions=["[TEST MODE] 测试失效条件"],
            alternative_directions=["[TEST MODE] 替代方向"],
        )

    # Unknown schema: try constructing with no args
    try:
        return schema()
    except Exception:
        return {}


class MockLLMClient(BaseLLMClient):
    """LLM client that returns mock responses for testing — zero API calls."""

    def get_llm(self) -> Any:
        return MockChatModel(model_name=self.model)

    def validate_model(self) -> bool:
        return True
