import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from src.api.main import create_app


@pytest.fixture
def client(test_settings):
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client


def test_get_settings(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "daily_direction_llm_provider" in data
    assert "wiki_llm_provider" in data
    assert "llm_provider_configs" in data
    assert "openai" in data["llm_provider_configs"]
    assert "scheduler_enabled" in data
    assert "daily_direction_notification_enabled" in data
    assert "notification_report_channels" in data
    assert "wechat_webhook_url" in data
    assert "feishu_webhook_url" in data
    assert "email_sender" in data
    assert "trade_commission_rate" in data
    assert "trade_min_commission" in data
    assert "trade_stamp_tax_rate" in data
    assert "trade_transfer_fee_rate" in data
    assert "ta_output_language" not in data


def test_patch_settings(client):
    resp = client.patch(
        "/api/settings",
        json={
            "scheduler_enabled": True,
            "daily_direction_llm_provider": "deepseek",
            "wiki_llm_provider": "kimi",
            "llm_provider_configs": {
                "kimi": {
                    "quick_model": "kimi-k2.6",
                    "deep_model": "kimi-k2.6",
                }
            },
            "daily_direction_notification_enabled": True,
            "notification_report_channels": "wechat,email",
            "wechat_webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
            "email_sender": "sender@example.com",
            "trade_commission_rate": 0.0003,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["scheduler_enabled"] is True
    assert data["daily_direction_llm_provider"] == "deepseek"
    assert data["wiki_llm_provider"] == "kimi"
    assert data["llm_provider_configs"]["kimi"]["quick_model"] == "kimi-k2.6"
    assert data["llm_provider_configs"]["kimi"]["deep_model"] == "kimi-k2.6"
    assert data["daily_direction_notification_enabled"] is True
    assert data["notification_report_channels"] == "wechat,email"
    assert data["wechat_webhook_url"].endswith("key=test")
    assert data["email_sender"] == "sender@example.com"
    assert data["trade_commission_rate"] == 0.0003


def test_patch_settings_persists_only_changed_fields(client, test_settings):
    env_path = test_settings.settings_env_path
    env_path.write_text("OPENAI_API_KEY=keep-me\n", encoding="utf-8")

    resp = client.patch(
        "/api/settings",
        json={"daily_direction_llm_provider": "deepseek"},
    )

    assert resp.status_code == 200
    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert "OPENAI_API_KEY=keep-me" in content
    assert "DAILY_DIRECTION_LLM_PROVIDER=deepseek" in content
    assert not any(line.startswith("LLM_PROVIDER=") for line in lines)
    assert not any(line.startswith("WIKI_LLM_PROVIDER=") for line in lines)


def test_patch_settings_persists_model_fields_for_restart(client, test_settings):
    resp = client.patch(
        "/api/settings",
        json={
            "llm_provider_configs": {
                "kimi": {
                    "quick_model": "custom-quick",
                    "deep_model": "custom-deep",
                }
            },
        },
    )

    assert resp.status_code == 200
    content = test_settings.settings_env_path.read_text(encoding="utf-8")
    assert "KIMI_QUICK_MODEL=custom-quick" in content
    assert "KIMI_DEEP_MODEL=custom-deep" in content

    from src.config import Settings

    reloaded = Settings(_env_file=test_settings.settings_env_path)
    assert reloaded.kimi_quick_model == "custom-quick"
    assert reloaded.kimi_deep_model == "custom-deep"


def test_patch_settings_keeps_provider_api_keys_independent(client, test_settings):
    test_settings.openai_api_key = "sk-openai"
    test_settings.deepseek_api_key = "sk-deepseek"
    test_settings.kimi_api_key = "sk-kimi"

    resp = client.patch(
        "/api/settings",
        json={
            "llm_provider_configs": {
                "kimi": {
                    "api_key": "sk-kimi-new",
                }
            },
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_provider_configs"]["openai"]["api_key"] == "sk-openai"
    assert data["llm_provider_configs"]["deepseek"]["api_key"] == "sk-deepseek"
    assert data["llm_provider_configs"]["kimi"]["api_key"] == "sk-kimi-new"
    assert test_settings.openai_api_key == "sk-openai"
    assert test_settings.deepseek_api_key == "sk-deepseek"
    assert test_settings.kimi_api_key == "sk-kimi-new"


def test_list_scheduled_tasks(client):
    resp = client.get("/api/settings/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    ids = {t["id"] for t in data}
    assert ids == {"analysis", "data_refresh", "sector_discovery"}


def test_update_scheduled_task(client):
    resp = client.patch("/api/settings/tasks/analysis", json={"enabled": True, "cron": "0 10 * * 1-5"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "analysis"
    assert data["enabled"] is True
    assert data["cron"] == "0 10 * * 1-5"


def test_run_scheduled_task(client):
    client.app.state.services.scheduler.run_task_now = AsyncMock(
        return_value={"success": True, "message": "ok"}
    )
    resp = client.post("/api/settings/tasks/sector_discovery/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == "sector_discovery"
    assert data["success"] is True


def test_update_unknown_task(client):
    resp = client.patch("/api/settings/tasks/unknown", json={"enabled": True})
    assert resp.status_code == 404


def test_get_llm_providers(client):
    resp = client.get("/api/settings/llm-providers")
    assert resp.status_code == 200
    data = resp.json()
    assert "providers" in data
    assert len(data["providers"]) >= 15
    ids = {p["id"] for p in data["providers"]}
    expected = {
        "openai", "deepseek", "anthropic", "google", "azure",
        "xai", "qwen", "qwen-cn", "glm", "glm-cn",
        "minimax", "minimax-cn", "openrouter", "kimi", "ollama",
    }
    assert expected.issubset(ids)

    # Spot-check DeepSeek defaults (must match catalog, not legacy aliases)
    deepseek = next(p for p in data["providers"] if p["id"] == "deepseek")
    assert deepseek["default_quick_model"] == "deepseek-v4-flash"
    assert deepseek["default_deep_model"] == "deepseek-v4-pro"
    assert deepseek["default_base_url"] == "https://api.deepseek.com"

    # Spot-check MiniMax defaults
    minimax = next(p for p in data["providers"] if p["id"] == "minimax")
    assert minimax["default_quick_model"] == "MiniMax-M3"
    assert minimax["default_deep_model"] == "MiniMax-M3"
    assert minimax["default_base_url"] == "https://api.minimax.io/v1"

    # Spot-check Kimi official endpoint
    kimi = next(p for p in data["providers"] if p["id"] == "kimi")
    assert kimi["default_base_url"] == "https://api.moonshot.ai/v1"
    assert kimi["default_quick_model"] == "kimi-k2.6"

    # Ollama does not require key
    ollama = next(p for p in data["providers"] if p["id"] == "ollama")
    assert ollama["requires_api_key"] is False
    assert ollama["api_key_env"] is None

    # Verify custom models are supported
    openai = next(p for p in data["providers"] if p["id"] == "openai")
    assert openai["supports_custom_model"] is True
