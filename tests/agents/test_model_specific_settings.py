import pytest

from src.config import Settings


def test_sector_discovery_uses_provider_catalog_deep_model(monkeypatch):
    from src.agents.sector_discovery import llm_utils

    captured = {}

    class FakeClient:
        def get_llm(self):
            return object()

    def fake_create_llm_client(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(llm_utils, "create_llm_client", fake_create_llm_client)

    settings = Settings(
        _env_file=None,
        daily_direction_llm_provider="deepseek",
        deepseek_api_key="fake-key",
    )

    llm_utils._get_llm(settings)

    assert captured["provider"] == "deepseek"
    assert captured["model"] == "deepseek-v4-pro"


@pytest.mark.asyncio
async def test_wiki_planner_uses_wiki_provider_quick_model(monkeypatch):
    import src.knowledge.wiki_planner as wiki_planner

    monkeypatch.delenv("KIMI_QUICK_MODEL", raising=False)
    captured = {}

    class FakeResponse:
        content = "{}"

    class FakeLLM:
        def invoke(self, messages):
            return FakeResponse()

    class FakeClient:
        def get_llm(self):
            return FakeLLM()

    def fake_create_llm_client(**kwargs):
        captured.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(
        "src.agents.tradingagents.llm_clients.factory.create_llm_client",
        fake_create_llm_client,
    )

    settings = Settings(
        _env_file=None,
        wiki_llm_provider="kimi",
        kimi_api_key="fake-key",
    )
    planner = wiki_planner.LLMWikiPlanner(settings)

    await planner._invoke_llm("prompt")

    assert captured["provider"] == "kimi"
    assert captured["model"] == "kimi-k2.6"
