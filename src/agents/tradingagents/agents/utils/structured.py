"""Shared helpers for invoking an agent with structured output and a graceful fallback.

The Portfolio Manager, Trader, and Research Manager all follow the same
canonical pattern:

1. At agent creation, wrap the LLM with ``with_structured_output(Schema)``
   so the model returns a typed Pydantic instance. If the provider does
   not support structured output (rare; mostly older Ollama models), the
   wrap is skipped and the agent uses free-text generation instead.
2. At invocation, run the structured call and render the result back to
   markdown. If the structured call itself fails for any reason
   (malformed JSON from a weak model, transient provider issue), fall
   back to a plain ``llm.invoke`` so the pipeline never blocks.

Centralising the pattern here keeps the agent factories small and ensures
all three agents log the same warnings when fallback fires.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None


def _prompt_with_json_hint(prompt: Any) -> Any:
    """Add a JSON hint required by some providers' json_object mode."""
    hint = "Return the structured response as a valid JSON object matching the schema."
    if isinstance(prompt, str):
        if "json" in prompt.lower():
            return prompt
        return f"{prompt}\n\n{hint}"

    if isinstance(prompt, list):
        patched = copy.deepcopy(prompt)
        for message in patched:
            content = getattr(message, "content", None)
            if isinstance(content, str) and "json" in content.lower():
                return prompt
            if isinstance(message, dict):
                dict_content = message.get("content")
                if isinstance(dict_content, str) and "json" in dict_content.lower():
                    return prompt

        for message in patched:
            if isinstance(message, dict) and message.get("role") == "system":
                message["content"] = f"{message.get('content', '')}\n\n{hint}"
                return patched
            if getattr(message, "type", "") == "system" and isinstance(getattr(message, "content", None), str):
                message.content = f"{message.content}\n\n{hint}"
                return patched
        patched.insert(0, {"role": "system", "content": hint})
        return patched

    return prompt


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(_prompt_with_json_hint(prompt))
            return render(result)
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    response = plain_llm.invoke(prompt)
    return response.content
