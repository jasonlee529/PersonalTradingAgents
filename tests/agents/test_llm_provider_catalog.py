from src.agents.tradingagents.llm_clients.api_key_env import PROVIDER_API_KEY_ENV
from src.agents.tradingagents.llm_clients.provider_catalog import (
    get_all_providers,
    get_api_key_field,
    get_default_base_url,
    get_provider_info,
    resolve_model,
)


def test_llm_provider_catalog_coverage():
    providers = get_all_providers()
    ids = {p.id for p in providers}
    expected = {
        "openai",
        "deepseek",
        "anthropic",
        "google",
        "azure",
        "xai",
        "qwen",
        "qwen-cn",
        "glm",
        "glm-cn",
        "minimax",
        "minimax-cn",
        "openrouter",
        "kimi",
        "ollama",
    }
    assert expected.issubset(ids)

    custom_only = {"azure", "openrouter", "ollama"}
    for provider in providers:
        assert provider.id
        assert provider.label
        assert provider.region in ("global", "china")
        assert provider.api_key_field or provider.id == "ollama"
        if provider.id not in custom_only:
            assert provider.default_quick_model
            assert provider.default_deep_model

    assert get_provider_info("deepseek").default_quick_model == "deepseek-v4-flash"
    assert get_provider_info("deepseek").default_deep_model == "deepseek-v4-pro"
    assert get_default_base_url("deepseek") == "https://api.deepseek.com"
    assert get_default_base_url("anthropic") == "https://api.anthropic.com/v1"
    assert get_default_base_url("google") == "https://generativelanguage.googleapis.com"
    assert get_default_base_url("openai") == "https://api.openai.com/v1"
    assert get_default_base_url("qwen-cn") == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert get_default_base_url("kimi") == "https://api.moonshot.ai/v1"
    assert get_api_key_field("kimi") == "kimi_api_key"
    assert PROVIDER_API_KEY_ENV["minimax-cn"] == "MINIMAX_CN_API_KEY"
    assert PROVIDER_API_KEY_ENV["ollama"] is None


def test_catalog_resolves_default_models_without_frontend_model_inputs():
    for provider in get_all_providers():
        data = provider.to_dict()
        assert "default_quick_model" in data
        assert "default_deep_model" in data
        assert "quick_models" not in data
        assert "deep_models" not in data

    assert resolve_model("openai", "quick") == "gpt-5-mini"
    assert resolve_model("openai", "deep") == "gpt-5"
