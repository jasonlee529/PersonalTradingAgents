"""Token usage estimation, actual-usage extraction, pricing lookup, and logging.

Designed to be lightweight: imports are deferred so the module can be
imported at module level without pulling heavy dependencies until a call
actually happens.
"""

from __future__ import annotations

import inspect
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing table
# ---------------------------------------------------------------------------
# Prices are per 1M tokens.  Currency is annotated per provider:
#   CNY = Chinese yuan (Kimi, DeepSeek, Qwen, GLM, MiniMax)
#   $ = USD (OpenAI, Anthropic, Google, xAI, Azure)
# Source: official pricing pages as of 2026-06-04.
# ---------------------------------------------------------------------------

PRICING_TABLE: Dict[str, Dict[str, Dict[str, float]]] = {
    # --- Kimi (Moonshot) ---
    "kimi": {
        "kimi-k3":        {"input": 15.0, "output": 60.0},
        "kimi-k2-5":      {"input": 5.0,  "output": 20.0},
        "kimi-k2":        {"input": 5.0,  "output": 20.0},
    },
    # --- DeepSeek ---
    "deepseek": {
        "deepseek-v4-pro":   {"input": 2.0,  "output": 8.0},
        "deepseek-v4-flash": {"input": 1.0,  "output": 4.0},
        "deepseek-chat":     {"input": 1.0,  "output": 4.0},   # V3.2
        "deepseek-reasoner": {"input": 4.0,  "output": 16.0},  # V3.2 thinking
    },
    # --- OpenAI ---
    "openai": {
        "gpt-5.5":          {"input": 5.0,   "output": 15.0},
        "gpt-5.5-pro":      {"input": 30.0,  "output": 180.0},
        "gpt-5.4":          {"input": 2.5,   "output": 10.0},
        "gpt-5.4-mini":     {"input": 0.15,  "output": 0.6},
        "gpt-5.4-nano":     {"input": 0.05,  "output": 0.2},
        "gpt-5.2":          {"input": 2.0,   "output": 8.0},
        "gpt-4.1":          {"input": 2.0,   "output": 8.0},
        "gpt-4o":           {"input": 2.5,   "output": 10.0},
        "gpt-4o-mini":      {"input": 0.15,  "output": 0.6},
    },
    # --- Anthropic ---
    "anthropic": {
        "claude-opus-4-7":   {"input": 15.0,  "output": 75.0},
        "claude-opus-4-6":   {"input": 15.0,  "output": 75.0},
        "claude-opus-4-5":   {"input": 15.0,  "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0,   "output": 15.0},
        "claude-sonnet-4-5": {"input": 3.0,   "output": 15.0},
        "claude-haiku-4-5":  {"input": 0.25,  "output": 1.25},
    },
    # --- Google (Gemini) ---
    "google": {
        "gemini-3.1-pro-preview": {"input": 1.25, "output": 10.0},
        "gemini-3-flash-preview":  {"input": 0.15, "output": 0.6},
        "gemini-2.5-pro":          {"input": 1.25, "output": 10.0},
        "gemini-2.5-flash":        {"input": 0.15, "output": 0.6},
        "gemini-2.5-flash-lite":   {"input": 0.075,"output": 0.3},
        "gemini-3.1-flash-lite":   {"input": 0.075,"output": 0.3},
    },
    # --- xAI (Grok) ---
    "xai": {
        "grok-4.20":                {"input": 5.0,  "output": 25.0},
        "grok-4.20-reasoning":      {"input": 10.0, "output": 50.0},
        "grok-4.20-non-reasoning":  {"input": 5.0,  "output": 25.0},
        "grok-4":                   {"input": 5.0,  "output": 25.0},
        "grok-4-fast-reasoning":    {"input": 3.0,  "output": 15.0},
        "grok-4-fast-non-reasoning":{"input": 1.5,  "output": 7.5},
    },
    # --- Qwen (Alibaba) ---
    "qwen": {
        "qwen3.6-plus": {"input": 4.0,  "output": 12.0},
        "qwen3.6-flash":{"input": 0.2,  "output": 0.6},
        "qwen3.5-plus": {"input": 3.0,  "output": 9.0},
        "qwen3.5-flash":{"input": 0.15, "output": 0.45},
        "qwen3-max":    {"input": 5.0,  "output": 15.0},
    },
    "qwen-cn": {
        "qwen3.6-plus": {"input": 2.0,  "output": 6.0},
        "qwen3.6-flash":{"input": 0.1,  "output": 0.3},
        "qwen3.5-plus": {"input": 1.5,  "output": 4.5},
        "qwen3.5-flash":{"input": 0.075,"output": 0.225},
        "qwen3-max":    {"input": 2.5,  "output": 7.5},
    },
    # --- GLM (Zhipu) ---
    "glm": {
        "glm-5.1":       {"input": 10.0, "output": 30.0},
        "glm-5":         {"input": 10.0, "output": 30.0},
        "glm-5-turbo":   {"input": 1.0,  "output": 3.0},
        "glm-4.7":       {"input": 5.0,  "output": 15.0},
        "glm-4.5-air":   {"input": 0.5,  "output": 1.5},
    },
    "glm-cn": {
        "glm-5.1":       {"input": 5.0,  "output": 15.0},
        "glm-5":         {"input": 5.0,  "output": 15.0},
        "glm-5-turbo":   {"input": 0.5,  "output": 1.5},
        "glm-4.7":       {"input": 2.5,  "output": 7.5},
        "glm-4.5-air":   {"input": 0.25, "output": 0.75},
    },
    # --- MiniMax ---
    "minimax": {
        "minimax-m2.7":           {"input": 2.0,  "output": 10.0},
        "minimax-m2.7-highspeed": {"input": 1.0,  "output": 5.0},
        "minimax-m2.5":           {"input": 1.5,  "output": 7.5},
        "minimax-m2.5-highspeed": {"input": 0.75, "output": 3.75},
        "minimax-m2.1":           {"input": 1.0,  "output": 5.0},
        "minimax-m2.1-highspeed": {"input": 0.5,  "output": 2.5},
        "minimax-m2":             {"input": 0.8,  "output": 4.0},
    },
    "minimax-cn": {
        "minimax-m2.7":           {"input": 1.0,  "output": 5.0},
        "minimax-m2.7-highspeed": {"input": 0.5,  "output": 2.5},
        "minimax-m2.5":           {"input": 0.75, "output": 3.75},
        "minimax-m2.5-highspeed": {"input": 0.375,"output": 1.875},
        "minimax-m2.1":           {"input": 0.5,  "output": 2.5},
        "minimax-m2.1-highspeed": {"input": 0.25, "output": 1.25},
        "minimax-m2":             {"input": 0.4,  "output": 2.0},
    },
    # --- Azure OpenAI (same as OpenAI, in USD) ---
    "azure": {
        "gpt-4o":       {"input": 2.5,  "output": 10.0},
        "gpt-4o-mini":  {"input": 0.15, "output": 0.6},
        "gpt-5.4":      {"input": 2.5,  "output": 10.0},
        "gpt-5.4-mini": {"input": 0.15, "output": 0.6},
    },
    # --- OpenRouter (varies by upstream, approximate) ---
    "openrouter": {
        "default": {"input": 1.0, "output": 4.0},
    },
    # --- Ollama (local, free) ---
    "ollama": {
        "default": {"input": 0.0, "output": 0.0},
    },
}


_CURRENCY_MAP = {
    "kimi": "CNY ",
    "deepseek": "CNY ",
    "openai": "$", "azure": "$",
    "anthropic": "$",
    "google": "$",
    "xai": "$",
    "qwen": "CNY ", "qwen-cn": "CNY ",
    "glm": "CNY ", "glm-cn": "CNY ",
    "minimax": "$", "minimax-cn": "CNY ",
    "openrouter": "$",
    "ollama": "$",
}


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

def _is_retryable(exc: Exception) -> bool:
    """Whether an exception warrants a single retry.

    Covers:
    - Network-level timeouts (httpx ReadTimeout, ConnectTimeout)
    - HTTP 5xx / 504 Gateway Timeout from OpenAI-compatible APIs
    - APIStatusError with status >= 500
    """
    exc_name = type(exc).__name__
    if exc_name in ("ReadTimeout", "ConnectTimeout", "TimeoutException"):
        return True

    # openai.APIStatusError and similar wrappers expose .status_code
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is not None and status >= 500:
        return True

    # Some SDKs embed the status in response.status
    response = getattr(exc, "response", None)
    if response is not None:
        status = getattr(response, "status_code", None) or getattr(response, "status", None)
        if status is not None and status >= 500:
            return True

    # Fallback: inspect the string for 504 / 502 / 503 / 500
    msg = str(exc).lower()
    for code in ("504", "502", "503", "500", "timeout", "gateway"):
        if code in msg:
            return True

    return False


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

def estimate_prompt_tokens(input_: Any, model: str) -> int:
    """Estimate token count for *input_* before the request is sent.

    Uses tiktoken when available (good enough for OpenAI-compatible models).
    Falls back to a character heuristic for other inputs.
    """
    messages = _input_to_messages(input_)
    if not messages:
        return 0

    try:
        return _estimate_with_tiktoken(messages, model)
    except Exception:
        return _estimate_fallback(messages)


def _input_to_messages(input_: Any) -> list:
    """Normalise a langchain LLM input to a list of message objects."""
    if isinstance(input_, list):
        return input_
    if hasattr(input_, "to_messages"):
        return input_.to_messages()
    return []


def _estimate_with_tiktoken(messages: list, model: str) -> int:
    import tiktoken

    # Map any model name to a tiktoken encoder.  gpt-4o is a safe
    # default for all OpenAI-compatible providers (approximation).
    encoder_name = "o200k_base"  # gpt-4o / gpt-4o-mini
    try:
        enc = tiktoken.get_encoding(encoder_name)
    except Exception:
        enc = tiktoken.encoding_for_model("gpt-4o")

    total = 0
    for msg in messages:
        content = _message_content(msg)
        if isinstance(content, str):
            total += len(enc.encode(content))
        elif isinstance(content, list):
            # Content blocks (e.g. text + image)
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += len(enc.encode(block.get("text", "")))
                elif isinstance(block, str):
                    total += len(enc.encode(block))
    return total


def _estimate_fallback(messages: list) -> int:
    """Rough fallback: Chinese ~2 chars/token, English ~4 chars/token."""
    total_chars = 0
    for msg in messages:
        content = _message_content(msg)
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total_chars += len(block.get("text", ""))
                elif isinstance(block, str):
                    total_chars += len(block)
    # Conservative: assume mixed content, ~2.5 chars per token
    return max(1, int(total_chars / 2.5))


def _message_content(msg: Any) -> Any:
    """Extract content from a BaseMessage or dict."""
    if hasattr(msg, "content"):
        return msg.content
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


# ---------------------------------------------------------------------------
# Usage extraction from response
# ---------------------------------------------------------------------------

def extract_usage_from_response(response: Any) -> Optional[Dict[str, int]]:
    """Pull token-usage dict from an AIMessage (or similar) response.

    Returns a dict with keys: prompt_tokens, completion_tokens, total_tokens.
    Returns None when the provider did not include usage metadata.
    """
    if response is None:
        return None

    # 1. LangChain usage_metadata (Anthropic, Google, newer OpenAI)
    usage_meta = getattr(response, "usage_metadata", None)
    if usage_meta:
        return {
            "prompt_tokens":     usage_meta.get("input_tokens", 0),
            "completion_tokens": usage_meta.get("output_tokens", 0),
            "total_tokens":      usage_meta.get("total_tokens", 0),
        }

    # 2. OpenAI-style response_metadata.token_usage
    resp_meta = getattr(response, "response_metadata", None)
    if resp_meta and isinstance(resp_meta, dict):
        token_usage = resp_meta.get("token_usage")
        if token_usage and isinstance(token_usage, dict):
            return {
                "prompt_tokens":     token_usage.get("prompt_tokens", 0),
                "completion_tokens": token_usage.get("completion_tokens", 0),
                "total_tokens":      token_usage.get("total_tokens", 0),
            }

    # 3. DeepSeek / some providers put it in additional_kwargs
    add_kwargs = getattr(response, "additional_kwargs", None)
    if add_kwargs and isinstance(add_kwargs, dict):
        usage = add_kwargs.get("usage")
        if usage and isinstance(usage, dict):
            return {
                "prompt_tokens":     usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens":      usage.get("total_tokens", 0),
            }

    return None


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

def get_model_pricing(provider: str, model: str) -> Optional[Dict[str, float]]:
    """Look up pricing for a (provider, model) pair.

    Falls back to "default" entry for the provider if the exact model
    is not listed.
    """
    provider_table = PRICING_TABLE.get(provider.lower())
    if not provider_table:
        return None
    price = provider_table.get(model.lower())
    if price is None:
        price = provider_table.get("default")
    return price


def calculate_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> tuple[float, str]:
    """Return (cost, currency_symbol) for the given token counts.

    Cost is in the provider's native currency unit (CNY or USD).
    Returns (0.0, "") when pricing is unknown.
    """
    price = get_model_pricing(provider, model)
    if price is None:
        return 0.0, ""

    currency = _CURRENCY_MAP.get(provider.lower(), "")
    cost = (
        prompt_tokens * price["input"] / 1_000_000
        + completion_tokens * price["output"] / 1_000_000
    )
    return cost, currency


# ---------------------------------------------------------------------------
# Agent-node detection
# ---------------------------------------------------------------------------

def _get_agent_node() -> Optional[str]:
    """Walk the call stack to find the agent node that triggered the LLM call.

    Looks for the first frame that is:
    - Not inside token_tracker or llm_clients (skip LLM internals)
    - Has a function name ending with '_node' (LangGraph node convention)
    - Or comes from the tradingagents.agents package
    """
    for frame_info in inspect.stack():
        filename = frame_info.filename.replace("\\", "/")
        # Skip our own LLM client internals
        if "token_tracker" in filename or "llm_clients" in filename:
            continue
        func_name = frame_info.function
        # LangGraph node functions typically end with '_node'
        if func_name.endswith("_node"):
            return func_name
        # Fallback: any function in the agents package
        if "tradingagents/agents" in filename:
            return func_name
    return None


# ---------------------------------------------------------------------------
# Logging helper
# ---------------------------------------------------------------------------

def log_llm_request(provider: str, model: str, prompt_tokens: int) -> None:
    """Emit a log line *before* the HTTP request is sent.

    This survives even when the request later times out or raises.
    """
    agent_node = _get_agent_node()
    node_part = f" agent_node={agent_node}" if agent_node else ""
    logger.info(
        f"LLM request | provider={provider} model={model}{node_part} "
        f"prompt_tokens=~{prompt_tokens}"
    )


def log_llm_response(
    provider: str,
    model: str,
    prompt_tokens: int,
    usage: Optional[Dict[str, int]],
    duration: float,
    error: Optional[str] = None,
) -> None:
    """Emit a log line *after* the response arrives (or fails)."""
    agent_node = _get_agent_node()
    node_part = f" agent_node={agent_node}" if agent_node else ""
    parts = [
        f"LLM response | provider={provider} model={model}{node_part}",
        f"prompt_tokens=~{prompt_tokens}",
        f"duration={duration:.1f}s",
    ]
    if error:
        parts.append(f"error={error}")
    if usage:
        pt = usage.get("prompt_tokens", 0)
        ct = usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", 0)
        parts.append(f"completion_tokens={ct} total_tokens={tt}")
        cost, currency = calculate_cost(provider, model, pt, ct)
        if cost > 0:
            parts.append(f"cost={currency}{cost:.4f}")
    logger.info(" ".join(parts))


# ---------------------------------------------------------------------------
# Decorator / wrapper for invoke() methods
# ---------------------------------------------------------------------------

def _wrap_invoke(original_invoke, provider_attr: str = "_provider_name"):
    """Return a wrapped invoke() that logs token usage.

    Usage inside a subclass::

        def invoke(self, input, config=None, **kwargs):
            return _wrap_invoke(super().invoke, "_provider_name")(self, input, config, **kwargs)

    Or, for classes that do not inherit from NormalizedChatOpenAI::

        def invoke(self, input, config=None, **kwargs):
            return _wrap_invoke(super().invoke, "_provider_name")(self, input, config, **kwargs)
    """

    def wrapped(self, input, config=None, **kwargs):
        provider = getattr(self, provider_attr, "unknown")
        model = getattr(self, "model_name", getattr(self, "model", "unknown"))

        prompt_tokens = estimate_prompt_tokens(input, model)
        log_llm_request(provider, model, prompt_tokens)

        start = time.monotonic()
        try:
            response = original_invoke(input, config, **kwargs)
            duration = time.monotonic() - start
            usage = extract_usage_from_response(response)
            log_llm_response(provider, model, prompt_tokens, usage, duration)
            return response
        except Exception as exc:
            duration = time.monotonic() - start
            error_msg = f"{type(exc).__name__}: {exc}"
            log_llm_response(provider, model, prompt_tokens, None, duration, error=error_msg)
            raise

    return wrapped
