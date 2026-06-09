import pytest
from unittest.mock import MagicMock, patch

from src.agents.quality_gate import (
    _hard_check_report,
    _llm_review_report,
    run_quality_gate,
    _get_analyst_report_fields,
    _get_analyst_display_names,
)


def test_hard_check_empty_report():
    grade, detail = _hard_check_report("market", "")
    assert grade == "F"
    assert "为空" in detail


def test_hard_check_short_report():
    grade, detail = _hard_check_report("market", "a" * 50)
    assert grade == "D"
    assert "过短" in detail


def test_hard_check_good_report():
    report = "| 指标 | 值 |\n|---|---|\n| PE | 15 |\n分析内容..."
    grade, detail = _hard_check_report("market", report + "x" * 300)
    assert grade == "A"


def test_hard_check_with_failure_markers():
    report = "无法获取数据" + " " * 10
    grade, detail = _hard_check_report("market", report)
    assert grade == "D"


def test_hard_check_missing_data():
    report = "x" * 250 + "[数据缺失]" * 4
    grade, detail = _hard_check_report("market", report)
    assert grade == "C"
    assert "数据缺失" in detail


def test_run_quality_gate_basic():
    state = {
        "trade_date": "2024-01-01",
        "company_of_interest": "600519",
        "market_report": "| 指标 | 值 |\n|---|---|\n| PE | 15 |\n" + "x" * 300,
        "sentiment_report": "",
    }
    result = run_quality_gate(state)
    assert "600519" in result
    assert "报告完整性审计" in result
    assert "[A]" in result
    assert "[F]" in result


def test_run_quality_gate_with_llm_review():
    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(return_value=MagicMock(content="建议补充数据源"))

    state = {
        "trade_date": "2024-01-01",
        "company_of_interest": "600519",
        "market_report": "",
    }
    result = run_quality_gate(state, llm_client=mock_llm)
    assert "LLM 复审建议" in result
    assert "建议补充数据源" in result
    assert mock_llm.invoke.call_count >= 1


def test_run_quality_gate_without_llm():
    state = {
        "trade_date": "2024-01-01",
        "company_of_interest": "600519",
        "market_report": "",
    }
    result = run_quality_gate(state, llm_client=None)
    assert "LLM 复审建议" not in result


def test_llm_review_report_handles_exception():
    mock_llm = MagicMock()
    mock_llm.invoke = MagicMock(side_effect=RuntimeError("API error"))

    result = _llm_review_report("market", "bad report", "F", "为空", mock_llm)
    assert "LLM 复审失败" in result


def test_get_analyst_report_fields_returns_dict():
    fields = _get_analyst_report_fields()
    assert isinstance(fields, dict)
    assert len(fields) > 0


def test_get_analyst_display_names_returns_dict():
    names = _get_analyst_display_names()
    assert isinstance(names, dict)
    assert len(names) > 0


def test_run_quality_gate_warn_count():
    state = {
        "trade_date": "2024-01-01",
        "company_of_interest": "600519",
        "market_report": "x" * 250 + "[数据缺失]" * 4,
    }
    result = run_quality_gate(state)
    assert "警告数" in result
    assert "[C]" in result
