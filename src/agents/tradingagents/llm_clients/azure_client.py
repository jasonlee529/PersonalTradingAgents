import logging
import os
import time
from typing import Any, Optional

from langchain_openai import AzureChatOpenAI

logger = logging.getLogger(__name__)

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "reasoning_effort",
    "callbacks", "http_client", "http_async_client",
)


class NormalizedAzureChatOpenAI(AzureChatOpenAI):
    """AzureChatOpenAI with normalized content output."""

    def invoke(self, input, config=None, **kwargs):
        from .token_tracker import (
            _is_retryable,
            estimate_prompt_tokens,
            extract_usage_from_response,
            log_llm_request,
            log_llm_response,
        )

        provider = getattr(self, "_provider_name", "unknown")
        model = getattr(self, "model_name", getattr(self, "model", "unknown"))
        prompt_tokens = estimate_prompt_tokens(input, model)
        log_llm_request(provider, model, prompt_tokens)

        start = time.monotonic()
        try:
            response = super().invoke(input, config, **kwargs)
            duration = time.monotonic() - start
            usage = extract_usage_from_response(response)
            log_llm_response(provider, model, prompt_tokens, usage, duration)
            return normalize_content(response)
        except Exception as exc:
            duration = time.monotonic() - start
            if _is_retryable(exc):
                logger.warning(
                    "LLM retry | provider=%s model=%s error=%s",
                    provider, model, exc,
                )
                log_llm_request(provider, model, prompt_tokens)
                start2 = time.monotonic()
                try:
                    response = super().invoke(input, config, **kwargs)
                    duration2 = time.monotonic() - start2
                    usage = extract_usage_from_response(response)
                    log_llm_response(provider, model, prompt_tokens, usage, duration2)
                    return normalize_content(response)
                except Exception as exc2:
                    duration2 = time.monotonic() - start2
                    log_llm_response(
                        provider, model, prompt_tokens, None, duration + duration2,
                        error=f"{type(exc2).__name__}: {exc2}",
                    )
                    raise
            log_llm_response(
                provider, model, prompt_tokens, None, duration,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise


class AzureOpenAIClient(BaseLLMClient):
    """Client for Azure OpenAI deployments.

    Requires environment variables:
        AZURE_OPENAI_API_KEY: API key
        AZURE_OPENAI_ENDPOINT: Endpoint URL (e.g. https://<resource>.openai.azure.com/)
        AZURE_OPENAI_DEPLOYMENT_NAME: Deployment name
        OPENAI_API_VERSION: API version (e.g. 2025-03-01-preview)
    """

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured AzureChatOpenAI instance."""
        self.warn_if_unknown_model()

        llm_kwargs = {
            "model": self.model,
            "azure_deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", self.model),
        }

        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        llm = NormalizedAzureChatOpenAI(**llm_kwargs)
        llm._provider_name = "azure"
        return llm

    def validate_model(self) -> bool:
        """Azure accepts any deployed model name."""
        return True
