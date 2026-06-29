import sys
import types

import pandas as pd
import pytest

from src.data.sources.akshare_source import AkshareSource


@pytest.mark.asyncio
async def test_akshare_balance_sheet_uses_ths_statement(monkeypatch):
    calls = {}

    def fake_debt(symbol, indicator):
        calls["symbol"] = symbol
        calls["indicator"] = indicator
        return pd.DataFrame(
            [
                {"报告期": "2026-03-31", "资产总计": 100},
                {"报告期": "2025-12-31", "资产总计": 90},
            ]
        )

    fake_akshare = types.SimpleNamespace(stock_financial_debt_ths=fake_debt)
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    result = await AkshareSource().get_balance_sheet("000001.SZ")

    assert calls == {"symbol": "000001", "indicator": "按报告期"}
    assert result[0]["source"] == "akshare"
    assert result[0]["资产总计"] == 100


@pytest.mark.asyncio
async def test_akshare_statement_failure_returns_none(monkeypatch):
    def fake_cash(symbol, indicator):
        raise RuntimeError("blocked")

    fake_akshare = types.SimpleNamespace(stock_financial_cash_ths=fake_cash)
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    result = await AkshareSource().get_cashflow("000001")

    assert result is None
