"""Tests for the mock LLM client used in test_mode."""

import sys
from pathlib import Path

# Ensure src/agents/ is on sys.path for tradingagents imports
_agents_dir = Path(__file__).resolve().parent.parent.parent / "src" / "agents"
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

from langchain_core.messages import AIMessage  # noqa: E402

from src.agents.tradingagents.llm_clients.factory import create_llm_client  # noqa: E402
from src.agents.tradingagents.llm_clients.mock_client import MockChatModel, MockLLMClient  # noqa: E402


def test_factory_returns_mock_when_test_mode():
    client = create_llm_client(
        provider="openai",
        model="gpt-4o",
        test_mode=True,
    )
    assert isinstance(client, MockLLMClient)


def test_mock_llm_client_get_llm():
    client = MockLLMClient("gpt-4o")
    llm = client.get_llm()
    assert isinstance(llm, MockChatModel)


def test_mock_chat_model_invoke_returns_placeholder():
    llm = MockChatModel()
    response = llm.invoke("some prompt")
    assert isinstance(response, AIMessage)
    assert "[TEST MODE]" in response.content


def test_mock_chat_model_bind_tools_returns_no_tool_calls():
    llm = MockChatModel()
    bound = llm.bind_tools([])
    response = bound.invoke("some prompt")
    assert isinstance(response, AIMessage)
    assert response.tool_calls == []


def test_mock_structured_output_research_plan():
    from tradingagents.agents.schemas import PortfolioRating, ResearchPlan

    llm = MockChatModel()
    structured = llm.with_structured_output(ResearchPlan)
    result = structured.invoke("prompt")

    assert isinstance(result, ResearchPlan)
    assert result.recommendation == PortfolioRating.HOLD
    assert "[TEST MODE]" in result.rationale


def test_mock_structured_output_trader_proposal():
    from tradingagents.agents.schemas import TraderAction, TraderProposal

    llm = MockChatModel()
    structured = llm.with_structured_output(TraderProposal)
    result = structured.invoke("prompt")

    assert isinstance(result, TraderProposal)
    assert result.action == TraderAction.HOLD


def test_mock_structured_output_portfolio_decision():
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    llm = MockChatModel()
    structured = llm.with_structured_output(PortfolioDecision)
    result = structured.invoke("prompt")

    assert isinstance(result, PortfolioDecision)
    assert result.rating == PortfolioRating.HOLD
    assert "[TEST MODE]" in result.executive_summary


def test_structured_prompt_adds_json_hint_to_string_prompt():
    from tradingagents.agents.utils.structured import _prompt_with_json_hint

    prompt = _prompt_with_json_hint("Make a portfolio decision.")

    assert "JSON object" in prompt


def test_structured_prompt_adds_json_hint_to_system_message():
    from tradingagents.agents.utils.structured import _prompt_with_json_hint

    messages = [
        {"role": "system", "content": "You are a trader."},
        {"role": "user", "content": "Make a decision."},
    ]

    patched = _prompt_with_json_hint(messages)

    assert "JSON object" in patched[0]["content"]
    assert "JSON object" not in messages[0]["content"]
