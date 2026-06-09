"""Canonical provider -> API-key env-var mapping.

A single source of truth for which environment variable holds the API
key for each supported LLM provider. Used by the CLI's interactive key
prompt (cli/utils.ensure_api_key) and by anything else that needs to
ask "does this provider require a key, and which env var is it?".

When adding a new provider, register it in provider_catalog.py so the
CLI flow prompts for it automatically instead of failing on first API call.
"""

from __future__ import annotations

from typing import Optional

from .provider_catalog import (
    get_api_key_env as _get_api_key_env_from_catalog,
    get_api_key_env_map,
)

# Re-export the canonical mapping for backward compatibility.
# The actual data lives in provider_catalog.py.
PROVIDER_API_KEY_ENV: dict[str, Optional[str]] = get_api_key_env_map()


def get_api_key_env(provider: str) -> Optional[str]:
    """Return the env var name for `provider`'s API key, or None if not applicable.

    Unknown providers also return None — callers should treat that as
    "no key check possible" rather than as "no key required".
    """
    return _get_api_key_env_from_catalog(provider)
