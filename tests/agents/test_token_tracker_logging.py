import logging

from src.agents.tradingagents.llm_clients.token_tracker import log_llm_response


def test_llm_response_cost_uses_ascii_currency(caplog):
    caplog.set_level(logging.INFO)

    log_llm_response(
        provider="kimi",
        model="kimi-k3",
        prompt_tokens=100,
        usage={"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
        duration=1.0,
    )

    assert "cost=CNY " in caplog.text
    assert "¥" not in caplog.text
