"""Helpers for passing market-specific rules through graph state."""
from __future__ import annotations

from typing import Any


def render_market_rules_section(state: dict[str, Any]) -> str:
    rules = str(state.get("market_rules") or "").strip()
    if not rules:
        profile = state.get("market_profile") or {}
        if isinstance(profile, dict):
            rules = str(profile.get("rules") or "").strip()
    if not rules:
        return ""
    return f"\n\nMarket-specific trading rules:\n{rules}\n"
