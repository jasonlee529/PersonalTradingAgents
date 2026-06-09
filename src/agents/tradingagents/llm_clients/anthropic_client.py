import logging
import re
import time
from typing import Any, Optional

from langchain_anthropic import ChatAnthropic

logger = logging.getLogger(__name__)

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client", "effort",
)

# Anthropic's extended-thinking ``effort`` parameter is accepted by Opus 4.5+
# and Sonnet 4.5+ only. Haiku (any version shipped to date) 400s with
# ``"This model does not support the effort parameter"`` (#831). Future
# ``claude-{opus,sonnet}-X-Y`` releases inherit effort support via the
# forward-compat pattern below; future Haiku stays excluded by default.
_EFFORT_EXACT = {
    "claude-mythos-preview",  # non-standard preview name; effort-capable
}
_EFFORT_PATTERN = re.compile(r"^claude-(opus|sonnet)-\d+-\d+$")


def _supports_effort(model: str) -> bool:
    """Whether Anthropic accepts the ``effort`` parameter for this model."""
    model_lc = model.lower()
    return model_lc in _EFFORT_EXACT or bool(_EFFORT_PATTERN.match(model_lc))


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
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


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key not in self.kwargs:
                continue
            if key == "effort" and not _supports_effort(self.model):
                continue
            llm_kwargs[key] = self.kwargs[key]

        llm = NormalizedChatAnthropic(**llm_kwargs)
        llm._provider_name = "anthropic"
        return llm

    def validate_model(self) -> bool:
        """Validate model for Anthropic."""
        return validate_model("anthropic", self.model)
