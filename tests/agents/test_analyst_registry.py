import sys
from pathlib import Path

# Ensure tradingagents package is on sys.path for imports
_agents_dir = Path(__file__).resolve().parent.parent.parent / "src" / "agents"
if str(_agents_dir) not in sys.path:
    sys.path.insert(0, str(_agents_dir))

import pytest
from src.agents.tradingagents.agents.analyst_registry import AnalystRegistry, AnalystEntry


def test_registry_discovers_market_analyst():
    reg = AnalystRegistry()
    entry = reg.get("market")
    assert entry is not None
    assert entry.label == "市场分析"
    assert entry.report_key == "market_report"


def test_registry_discovers_all_analysts():
    reg = AnalystRegistry()
    names = reg.names()
    assert "market" in names
    assert "news" in names
    assert "fundamentals" in names


def test_registry_default_names():
    reg = AnalystRegistry()
    defaults = reg.default_names()
    assert defaults[0] == "market"
    assert defaults == ["market", "social", "news", "fundamentals", "catalyst", "flow_risk"]
    assert "lockup" not in defaults


def test_entry_to_dict():
    entry = AnalystEntry(
        name="test",
        label="Test",
        report_key="test_report",
        llm_type="quick",
        factory=lambda: None,
        module_name="mod",
    )
    d = entry.to_dict()
    assert d["name"] == "test"
    assert d["label"] == "Test"
