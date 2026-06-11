"""Unified LLM provider catalog.

Single source of truth for provider metadata: labels, regions, default base URLs,
API-key env vars, model defaults, and model option lists. Consumed by the
settings API, CLI model picker, and LLM client construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    region: str
    default_base_url: str
    api_key_env: Optional[str]
    api_key_field: str
    default_quick_model: str
    default_deep_model: str
    requires_api_key: bool
    supports_custom_model: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "region": self.region,
            "api_key_field": self.api_key_field,
            "api_key_env": self.api_key_env,
            "default_base_url": self.default_base_url,
            "default_quick_model": self.default_quick_model,
            "default_deep_model": self.default_deep_model,
            "requires_api_key": self.requires_api_key,
            "supports_custom_model": self.supports_custom_model,
        }


_PROVIDER_REGISTRY: list[ProviderInfo] = [
    ProviderInfo(
        id="openai",
        label="OpenAI",
        region="global",
        default_base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        api_key_field="openai_api_key",
        default_quick_model="gpt-5-mini",
        default_deep_model="gpt-5",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="deepseek",
        label="DeepSeek",
        region="global",
        default_base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        api_key_field="deepseek_api_key",
        default_quick_model="deepseek-v4-flash",
        default_deep_model="deepseek-v4-pro",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="anthropic",
        label="Anthropic",
        region="global",
        default_base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        api_key_field="anthropic_api_key",
        default_quick_model="claude-sonnet-4-6",
        default_deep_model="claude-opus-4-8",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="google",
        label="Google",
        region="global",
        default_base_url="https://generativelanguage.googleapis.com",
        api_key_env="GOOGLE_API_KEY",
        api_key_field="google_api_key",
        default_quick_model="gemini-2.5-flash",
        default_deep_model="gemini-2.5-pro",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="azure",
        label="Azure OpenAI",
        region="global",
        # Azure OpenAI endpoints are resource-specific, so there is no single
        # canonical default base URL to hardcode here.
        default_base_url="",
        api_key_env="AZURE_OPENAI_API_KEY",
        api_key_field="azure_openai_api_key",
        default_quick_model="",
        default_deep_model="",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="xai",
        label="xAI",
        region="global",
        default_base_url="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        api_key_field="xai_api_key",
        default_quick_model="grok-4.3",
        default_deep_model="grok-4.3",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="qwen",
        label="Qwen",
        region="global",
        default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        api_key_field="dashscope_api_key",
        default_quick_model="qwen-flash",
        default_deep_model="qwen-plus",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="qwen-cn",
        label="Qwen (CN)",
        region="china",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_CN_API_KEY",
        api_key_field="dashscope_cn_api_key",
        default_quick_model="qwen-flash",
        default_deep_model="qwen-plus",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="glm",
        label="GLM",
        region="global",
        default_base_url="https://api.z.ai/api/paas/v4/",
        api_key_env="ZHIPU_API_KEY",
        api_key_field="zhipu_api_key",
        default_quick_model="glm-4.5-air",
        default_deep_model="glm-4.5",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="glm-cn",
        label="GLM (CN)",
        region="china",
        default_base_url="https://open.bigmodel.cn/api/paas/v4/",
        api_key_env="ZHIPU_CN_API_KEY",
        api_key_field="zhipu_cn_api_key",
        default_quick_model="glm-4.5-air",
        default_deep_model="glm-4.5",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="minimax",
        label="MiniMax",
        region="global",
        default_base_url="https://api.minimax.io/v1",
        api_key_env="MINIMAX_API_KEY",
        api_key_field="minimax_api_key",
        default_quick_model="MiniMax-M3",
        default_deep_model="MiniMax-M3",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="minimax-cn",
        label="MiniMax (CN)",
        region="china",
        default_base_url="https://api.minimaxi.com/v1",
        api_key_env="MINIMAX_CN_API_KEY",
        api_key_field="minimax_cn_api_key",
        default_quick_model="MiniMax-M3",
        default_deep_model="MiniMax-M3",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="openrouter",
        label="OpenRouter",
        region="global",
        default_base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        api_key_field="openrouter_api_key",
        default_quick_model="",
        default_deep_model="",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="kimi",
        label="Kimi",
        region="global",
        default_base_url="https://api.moonshot.cn/v1",
        api_key_env="KIMI_API_KEY",
        api_key_field="kimi_api_key",
        default_quick_model="kimi-k2.6",
        default_deep_model="kimi-k2.6",
        requires_api_key=True,
    ),
    ProviderInfo(
        id="ollama",
        label="Ollama",
        region="global",
        default_base_url="http://localhost:11434/v1",
        api_key_env=None,
        api_key_field="",
        default_quick_model="",
        default_deep_model="",
        requires_api_key=False,
    ),
]

_PROVIDER_MAP: dict[str, ProviderInfo] = {p.id: p for p in _PROVIDER_REGISTRY}


def get_provider_info(provider: str) -> Optional[ProviderInfo]:
    """Return metadata for a provider id, or None if unknown."""
    return _PROVIDER_MAP.get(provider.lower())


def get_all_providers() -> list[ProviderInfo]:
    """Return all registered providers in definition order."""
    return list(_PROVIDER_REGISTRY)


def list_provider_ids() -> list[str]:
    """Return all registered provider ids."""
    return [p.id for p in _PROVIDER_REGISTRY]


def get_api_key_env(provider: str) -> Optional[str]:
    """Return the env-var name for a provider's API key, or None."""
    info = get_provider_info(provider)
    return info.api_key_env if info else None


def get_api_key_env_map() -> dict[str, Optional[str]]:
    """Return provider -> API-key env var mapping for compatibility callers."""
    return {p.id: p.api_key_env for p in _PROVIDER_REGISTRY}


def get_api_key_field(provider: str) -> str:
    """Return the Settings field name that stores a provider's API key."""
    info = get_provider_info(provider)
    return info.api_key_field if info else ""


def get_default_base_url(provider: str) -> str:
    """Return the default base URL for a provider, or empty string."""
    info = get_provider_info(provider)
    return info.default_base_url if info else ""


def get_default_models(provider: str) -> tuple[str, str]:
    """Return (default_quick_model, default_deep_model) for a provider."""
    info = get_provider_info(provider)
    if info:
        return info.default_quick_model, info.default_deep_model
    return ("", "")


def get_model_settings_field(provider: str, llm_type: str) -> str:
    """Return the Settings field storing a provider-specific model override."""
    normalized = llm_type.lower()
    if normalized not in ("quick", "deep"):
        raise ValueError(f"Unsupported LLM type: {llm_type}")
    return f"{provider.lower().replace('-', '_')}_{normalized}_model"


def resolve_model(provider: str, llm_type: str) -> str:
    """Resolve the default model for a provider and logical LLM role.

    ``llm_type`` must be ``quick`` or ``deep``. Model names are intentionally
    sourced only from this catalog so callers do not depend on per-user model
    settings.
    """
    info = get_provider_info(provider)
    if not info:
        raise ValueError(f"Unsupported LLM provider: {provider}")

    normalized = llm_type.lower()
    if normalized == "quick":
        model = info.default_quick_model
    elif normalized == "deep":
        model = info.default_deep_model
    else:
        raise ValueError(f"Unsupported LLM type: {llm_type}")

    if not model:
        raise ValueError(
            f"No default {normalized} model configured for LLM provider '{provider}'."
        )
    return model
