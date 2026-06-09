"""Dynamic analyst discovery and registry.

Scans tradingagents.agents.analysts/*.py for modules
exposing __analyst_name__, __analyst_label__, etc.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Ensure src/agents/ is on sys.path so tradingagents package is importable
_agents_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

ANALYSTS_DIR = Path(__file__).resolve().parent / "analysts"


class AnalystEntry:
    def __init__(
        self,
        name: str,
        label: str,
        report_key: str,
        llm_type: str,
        factory: Callable,
        module_name: str,
    ):
        self.name = name
        self.label = label
        self.report_key = report_key
        self.llm_type = llm_type
        self.factory = factory
        self.module_name = module_name

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "report_key": self.report_key,
            "llm_type": self.llm_type,
        }


class AnalystRegistry:
    """Singleton registry of discovered analysts."""

    _instance = None
    _entries: dict[str, AnalystEntry] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._discover()
        return cls._instance

    @classmethod
    def _discover(cls) -> None:
        cls._entries = {}
        if not ANALYSTS_DIR.exists():
            logger.warning("Analysts directory not found: %s", ANALYSTS_DIR)
            return

        for py_file in sorted(ANALYSTS_DIR.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"tradingagents.agents.analysts.{py_file.stem}"
            try:
                mod = importlib.import_module(module_name)
                name = getattr(mod, "__analyst_name__", None)
                if name is None:
                    continue
                entry = AnalystEntry(
                    name=name,
                    label=getattr(mod, "__analyst_label__", name),
                    report_key=getattr(mod, "__analyst_report_key__", f"{name}_report"),
                    llm_type=getattr(mod, "__analyst_llm_type__", "quick"),
                    factory=getattr(mod, f"create_{py_file.stem}"),
                    module_name=module_name,
                )
                cls._entries[name] = entry
                logger.debug("Registered analyst: %s", name)
            except Exception as e:
                logger.warning("Failed to load analyst %s: %s", module_name, e)

    @classmethod
    def list(cls) -> list[AnalystEntry]:
        return list(cls._entries.values())

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._entries.keys())

    @classmethod
    def get(cls, name: str) -> AnalystEntry | None:
        return cls._entries.get(name)

    @classmethod
    def default_names(cls) -> list[str]:
        """Default analyst set tuned for the A-share workflow."""
        all_names = cls.names()
        preferred = ["market", "social", "news", "fundamentals", "catalyst", "flow_risk"]
        result = [n for n in preferred if n in all_names]
        return result
