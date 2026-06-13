import logging
import os
import time
from typing import Any, Optional

import httpx
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

from .api_key_env import get_api_key_env
from .base_client import BaseLLMClient, normalize_content
from .capabilities import get_capabilities
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output and capability-aware binding.

    The Responses API returns content as a list of typed blocks
    (reasoning, text, etc.). ``invoke`` normalizes to string for
    consistent downstream handling.

    ``with_structured_output`` consults the per-model capability table
    (``capabilities.get_capabilities``) to pick the method and to decide
    whether ``tool_choice`` may be sent. Models that reject ``tool_choice``
    (e.g. DeepSeek V4 and reasoner — per their official tool-calling
    guide) still bind the schema as a tool, but no ``tool_choice``
    parameter is sent.

    Provider-specific quirks beyond structured-output (e.g. DeepSeek's
    reasoning_content roundtrip) live in subclasses so this base class
    stays small.
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

    def with_structured_output(self, schema, *, method=None, **kwargs):
        caps = get_capabilities(self.model_name)
        if caps.preferred_structured_method == "none":
            raise NotImplementedError(
                f"{self.model_name} has no structured-output method available; "
                f"agent factories will fall back to free-text generation."
            )
        method = method or caps.preferred_structured_method
        # When the model rejects tool_choice, suppress langchain's hardcoded
        # value. The schema is still bound as a tool — exactly what
        # DeepSeek's official tool-calling examples do.
        if method == "function_calling" and not caps.supports_tool_choice:
            kwargs.setdefault("tool_choice", None)
        return super().with_structured_output(schema, method=method, **kwargs)


def _input_to_messages(input_: Any) -> list:
    """Normalise a langchain LLM input to a list of message objects.

    Accepts a list of messages, a ``ChatPromptValue`` (from a
    ChatPromptTemplate), or anything else (treated as no messages).
    Used by providers that need to walk the outgoing message history;
    in particular DeepSeek thinking-mode propagation must work for
    both bare-list invocations and ChatPromptTemplate-driven ones, so
    treating only ``list`` here would silently skip half the call sites.
    """
    if isinstance(input_, list):
        return input_
    if hasattr(input_, "to_messages"):
        return input_.to_messages()
    return []


class DeepSeekChatOpenAI(NormalizedChatOpenAI):
    """DeepSeek-specific overrides on top of the OpenAI-compatible client.

    Thinking-mode round-trip is the only DeepSeek-specific behavior that
    stays here. When DeepSeek's thinking models return a response with
    ``reasoning_content``, that field must be echoed back as part of the
    assistant message on the next turn or the API fails with HTTP 400.
    ``_create_chat_result`` captures it on receive and
    ``_get_request_payload`` re-attaches it on send.

    Tool-choice handling for V4 and reasoner — those models reject the
    ``tool_choice`` parameter — is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        outgoing = payload.get("messages", [])
        for message_dict, message in zip(outgoing, _input_to_messages(input_)):
            if not isinstance(message, AIMessage):
                continue
            reasoning = message.additional_kwargs.get("reasoning_content")
            if reasoning is not None:
                message_dict["reasoning_content"] = reasoning
        return payload

    def _create_chat_result(self, response, generation_info=None):
        chat_result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        )
        for generation, choice in zip(
            chat_result.generations, response_dict.get("choices", [])
        ):
            reasoning = choice.get("message", {}).get("reasoning_content")
            if reasoning is not None:
                generation.message.additional_kwargs["reasoning_content"] = reasoning
        return chat_result


class MinimaxChatOpenAI(NormalizedChatOpenAI):
    """MiniMax-specific overrides on top of the OpenAI-compatible client.

    M2.x reasoning models embed ``<think>...</think>`` blocks directly in
    ``message.content`` by default, which would pollute saved reports.
    Per platform.minimax.io/docs/api-reference/text-openai-api, setting
    ``reasoning_split=True`` in the request body redirects the thinking
    block into ``reasoning_details`` so ``content`` stays clean.

    The flag is gated by ``ModelCapabilities.requires_reasoning_split``
    because non-reasoning MiniMax endpoints (Coding Plan, MiniMax-Text-01)
    reject the parameter via the openai SDK's strict kwarg validation
    (#826).

    Tool-choice handling for M2.x — those models accept only the string
    enum ``{"none", "auto"}`` and reject langchain's function-spec dict —
    is handled by the capability dispatch in
    ``NormalizedChatOpenAI.with_structured_output``, not here.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if get_capabilities(self.model_name).requires_reasoning_split:
            payload.setdefault("reasoning_split", True)
        return payload


class LlamaCppChatOpenAI(NormalizedChatOpenAI):
    """llama.cpp-specific overrides for structured output.

    llama-server exposes an OpenAI-compatible surface, but its tool calling
    path is more brittle than a native OpenAI endpoint. In practice, the
    generic function-calling route can inject a ``tool_choice`` object that
    llama.cpp rejects for some chat templates / models. For this provider we
    force JSON mode so structured-output users stay on the safer path.
    """

    def bind_tools(
        self,
        tools,
        *,
        tool_choice=None,
        strict=None,
        parallel_tool_calls=None,
        response_format=None,
        **kwargs,
    ):
        # llama.cpp's OpenAI-compatible chat endpoint is workable for plain
        # chat and JSON-mode structured output, but its tool-calling path is
        # brittle in LangChain. Returning the base model here keeps the pipeline
        # on the stable path instead of emitting tool-calling payloads that can
        # trigger 502s from the server.
        logger.warning(
            "llamacpp: tool binding disabled for stability; using plain chat instead"
        )
        return self

    def with_structured_output(self, schema, *, method=None, **kwargs):
        kwargs.setdefault("tool_choice", None)
        return super().with_structured_output(schema, method="json_mode", **kwargs)


# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

from .provider_catalog import get_default_base_url, list_provider_ids


def _resolve_provider_base_url(provider: str) -> Optional[str]:
    """Default base URL for ``provider``, with env-var overrides where defined.

    Currently only local OpenAI-compatible runtimes support env-var overrides
    (``OLLAMA_BASE_URL`` for Ollama and ``LLAMACPP_BASE_URL`` for llama.cpp),
    so users can point the provider at a remote server without editing code.
    The check is call-time, not import-time, so tests that monkeypatch the env
    after import behave correctly.
    """
    if provider == "ollama":
        env_url = os.environ.get("OLLAMA_BASE_URL")
        if env_url:
            return env_url
    if provider == "llamacpp":
        env_url = os.environ.get("LLAMACPP_BASE_URL")
        if env_url:
            return env_url
    return get_default_base_url(provider) or None


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # Provider-specific base URL and auth. An explicit base_url on the
        # client (e.g. a corporate proxy) takes precedence over the
        # provider default so users can route through their own gateway.
        if self.provider in list_provider_ids() and get_default_base_url(self.provider):
            llm_kwargs["base_url"] = self.base_url or _resolve_provider_base_url(self.provider)
            api_key_env = get_api_key_env(self.provider)
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                else:
                    raise ValueError(
                        f"API key for provider '{self.provider}' is not set. "
                        f"Please set the {api_key_env} environment variable "
                        f"(e.g. add {api_key_env}=your_key to your .env file)."
                    )
            else:
                llm_kwargs["api_key"] = self.provider
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # Local OpenAI-compatible servers (Ollama / llama.cpp) should not
        # inherit system proxy settings. On Windows, httpx can otherwise route
        # localhost requests through a corporate proxy and surface 502s even
        # though the local server is healthy.
        if self.provider in ("ollama", "llamacpp"):
            llm_kwargs.setdefault("http_client", httpx.Client(trust_env=False))
            llm_kwargs.setdefault("http_async_client", httpx.AsyncClient(trust_env=False))

        # Native OpenAI: use Responses API for consistent behavior across
        # all model families. Third-party providers use Chat Completions.
        if self.provider == "openai":
            llm_kwargs["use_responses_api"] = True

        # Provider-specific quirks live in their own subclasses so the
        # base NormalizedChatOpenAI stays free of provider branches.
        if self.provider == "deepseek":
            chat_cls = DeepSeekChatOpenAI
        elif self.provider == "kimi":
            # Kimi thinking-mode models need reasoning_content round-trip
            # echo (same mechanics as DeepSeek) plus tool_choice suppression.
            chat_cls = DeepSeekChatOpenAI
        elif self.provider in ("minimax", "minimax-cn"):
            chat_cls = MinimaxChatOpenAI
        elif self.provider == "llamacpp":
            chat_cls = LlamaCppChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
        llm = chat_cls(**llm_kwargs)
        llm._provider_name = self.provider
        return llm

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
