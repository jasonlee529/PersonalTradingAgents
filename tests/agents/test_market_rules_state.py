import sys
from pathlib import Path

from langchain_core.messages import AIMessage

agents_dir = Path(__file__).resolve().parents[2] / "src" / "agents"
if str(agents_dir) not in sys.path:
    sys.path.insert(0, str(agents_dir))


class PromptCapturingLLM:
    def __init__(self):
        self.prompts = []

    def with_structured_output(self, schema):
        raise NotImplementedError

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return AIMessage(content="captured")


def test_trader_reads_market_rules_from_state():
    from tradingagents.agents.trader.trader import create_trader

    llm = PromptCapturingLLM()
    node = create_trader(llm)

    result = node(
        {
            "company_of_interest": "600519",
            "asset_type": "stock",
            "investment_plan": "hold",
            "market_rules": "A股市场交易规则: T+1",
        }
    )

    assert result["trader_investment_plan"] == "captured"
    assert "A股市场交易规则" in llm.prompts[0][0]["content"]


def test_portfolio_manager_reads_market_rules_from_state():
    from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager

    llm = PromptCapturingLLM()
    node = create_portfolio_manager(llm)
    risk_state = {
        "history": "risk debate",
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "count": 0,
    }

    result = node(
        {
            "company_of_interest": "600519",
            "investment_plan": "hold",
            "trader_investment_plan": "hold",
            "risk_debate_state": risk_state,
            "market_profile": {"rules": "A股市场交易规则: T+1"},
        }
    )

    assert result["final_trade_decision"] == "captured"
    assert "A股市场交易规则" in llm.prompts[0]
