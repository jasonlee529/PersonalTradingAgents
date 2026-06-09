import logging
import time
from typing import Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with normalized content output.

    Gemini 3 models return content as list of typed blocks.
    This normalizes to string for consistent downstream handling.
    """

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


class GoogleClient(BaseLLMClient):
    """Client for Google Gemini models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatGoogleGenerativeAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Unified api_key maps to provider-specific google_api_key
        google_api_key = self.kwargs.get("api_key") or self.kwargs.get("google_api_key")
        if google_api_key:
            llm_kwargs["google_api_key"] = google_api_key

        # Map thinking_level to appropriate API param based on model
        # Gemini 3 Pro: low, high
        # Gemini 3 Flash: minimal, low, medium, high
        # Gemini 2.5: thinking_budget (0=disable, -1=dynamic)
        thinking_level = self.kwargs.get("thinking_level")
        if thinking_level:
            model_lower = self.model.lower()
            if "gemini-3" in model_lower:
                # Gemini 3 Pro doesn't support "minimal", use "low" instead
                if "pro" in model_lower and thinking_level == "minimal":
                    thinking_level = "low"
                llm_kwargs["thinking_level"] = thinking_level
            else:
                # Gemini 2.5: map to thinking_budget
                llm_kwargs["thinking_budget"] = -1 if thinking_level == "high" else 0

        llm = NormalizedChatGoogleGenerativeAI(**llm_kwargs)
        llm._provider_name = "google"
        return llm

    def validate_model(self) -> bool:
        """Validate model for Google."""
        return validate_model("google", self.model)
