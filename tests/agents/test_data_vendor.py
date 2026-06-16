import pytest
from unittest.mock import MagicMock
from src.agents.data_vendor import DataVendor


class FakeCollector:
    async def get_kline(self, code, period="1d", limit=800):
        return [
            {"date": "2024-01-01", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10000},
        ]

    async def get_fundamentals(self, code):
        return {"symbol": code, "pe": 15.0}

    async def get_global_news(self, look_back_days=7, limit=10):
        return [{"time": "2026-06-01", "title": f"{look_back_days}/{limit}", "source": "cls"}]

    async def get_balance_sheet(self, code):
        return None

    async def get_cashflow(self, code):
        return None

    async def get_income_statement(self, code):
        return None


@pytest.fixture
def vendor():
    return DataVendor(FakeCollector())


def test_normalize_ticker_used_in_get_stock_data(vendor):
    """Verify .SH/.SZ/.BJ suffixes are stripped via normalize_ticker."""
    result = vendor.get_stock_data("600519.SH", "2024-01-01", "2024-01-01")
    assert "600519" in result
    assert ".SH" not in result


def test_normalize_ticker_used_in_get_fundamentals(vendor):
    result = vendor.get_fundamentals("000001.SZ")
    assert "000001" in result
    assert ".SZ" not in result


def test_run_executes_coroutine(vendor):
    async def coro():
        return 42
    assert vendor._run(coro()) == 42


def test_run_propagates_exception(vendor):
    async def bad():
        raise ValueError("boom")
    with pytest.raises(ValueError, match="boom"):
        vendor._run(bad())


def test_get_global_news_accepts_tool_signature(vendor):
    result = vendor.get_global_news("2026-06-01", 3, 5)
    assert "3/5" in result


def test_get_global_news_accepts_legacy_signature(vendor):
    result = vendor.get_global_news(2, 4)
    assert "2/4" in result


def test_missing_balance_sheet_is_marked_as_data_coverage_not_bearish(vendor):
    result = vendor.get_balance_sheet("000001.SZ")
    assert "Data coverage status: unavailable" in result
    assert "not as evidence of weak balance-sheet quality" in result


def test_missing_cashflow_is_marked_as_data_coverage_not_bearish(vendor):
    result = vendor.get_cashflow("000001.SZ")
    assert "Data coverage status: unavailable" in result
    assert "not as evidence of weak cash generation" in result


def test_missing_income_statement_is_marked_as_data_coverage_not_bearish(vendor):
    result = vendor.get_income_statement("000001.SZ")
    assert "Data coverage status: unavailable" in result
    assert "not as evidence of poor profitability" in result
