"""回测引擎单元测试。

使用模拟的 collector 避免真实网络请求，验证回测流程和绩效计算。
"""

from datetime import date, timedelta

import pandas as pd

from src.strategies.backtest import BacktestConfig, BacktestEngine
from src.strategies.risk import RiskConfig


def _day_str(offset: int) -> str:
    return (date(2024, 1, 1) + timedelta(days=offset)).strftime("%Y-%m-%d")


class MockCollector:
    """模拟 DataCollector，返回构造的 K 线数据。"""

    def __init__(self, kline_data: dict[str, list[dict]]):
        self._kline = kline_data

    @staticmethod
    def _infer_market(symbol: str) -> str:
        if symbol.startswith("6"):
            return "sh"
        return "sz"

    async def get_market_list(self, trade_date: str = "", refresh: bool = False):
        rows = []
        for symbol, kline in self._kline.items():
            last = kline[-1]
            rows.append({
                "symbol": symbol, "name": f"股票{symbol}",
                "price": last["close"], "turnover": last["volume"] * last["close"],
                "change_pct": 0,
            })
        return rows, ""

    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 120):
        data = self._kline.get(symbol)
        if data is None:
            return None
        return data[-limit:]


def _build_uptrend_kline(symbol: str, n: int = 78) -> list[dict]:
    """构造一个有回踩+放量突破形态的 K 线。"""
    closes = [0.0] * n
    volumes = [0] * n
    for i in range(56):
        closes[i] = 10.0 + i * 0.02
        volumes[i] = 5000
    closes[56] = 11.0
    closes[57] = 12.0
    closes[58] = 13.0
    closes[59] = 13.0 * 1.10
    for i in range(56, 60):
        volumes[i] = 15000
    pullback_c = [14.0, 13.5, 12.8, 12.2, 11.8, 11.5, 11.6, 11.7, 11.8, 11.9]
    pullback_v = [8000, 7000, 6000, 5000, 4500, 4000, 4200, 4400, 4600, 4800]
    for j in range(10):
        closes[60 + j] = pullback_c[j]
        volumes[60 + j] = pullback_v[j]
    closes[70] = closes[69] * 1.10
    volumes[70] = 12000
    for i in range(71, 77):
        closes[i] = 12.0 + (i % 3) * 0.1
        volumes[i] = 4500 + (i % 3) * 200
    closes[77] = 12.8
    volumes[77] = 12000

    rows = []
    opens = [c * 0.997 for c in closes]
    opens[77] = 12.3
    for i in range(n):
        rows.append({
            "date": _day_str(i),
            "open": round(opens[i], 3),
            "high": round(closes[i] * 1.02, 3),
            "low": round(closes[i] * 0.98, 3),
            "close": round(closes[i], 3),
            "volume": int(volumes[i]),
            "turnover": round(closes[i] * volumes[i], 2),
            "change_pct": 0.0,
        })
    return rows


def test_backtest_basic_run():
    """基本回测流程应正常完成并返回结果。"""
    kline_data = {
        "600001": _build_uptrend_kline("600001"),
        "600002": _build_uptrend_kline("600002"),
    }
    collector = MockCollector(kline_data)
    engine = BacktestEngine(collector)

    config = BacktestConfig(
        strategy_id="strong_pullback",
        start_date="",
        end_date="",
        symbols=["600001", "600002"],
        initial_capital=1_000_000,
        kline_limit=100,
        risk_config=RiskConfig(max_holdings=5, max_position_pct=0.20),
    )
    result = engine.run.__wrapped__ if hasattr(engine.run, "__wrapped__") else None
    # run 是 async，需要 await
    import asyncio
    result = asyncio.run(engine.run(config))

    assert result.error == "" or result.trading_days > 0
    assert result.universe_size == 2
    assert len(result.equity_curve) > 0
    assert "total_return_pct" in result.metrics


def test_backtest_unknown_strategy():
    """未知策略应返回错误。"""
    collector = MockCollector({})
    engine = BacktestEngine(collector)
    config = BacktestConfig(strategy_id="not_exist", symbols=["600001"])

    import asyncio
    result = asyncio.run(engine.run(config))
    assert result.error != ""
    assert "not_exist" in result.error


def test_backtest_no_symbols():
    """空股票池应返回错误。"""
    collector = MockCollector({})
    engine = BacktestEngine(collector)
    config = BacktestConfig(strategy_id="strong_pullback", symbols=["999999"])

    import asyncio
    result = asyncio.run(engine.run(config))
    # 999999 不在 kline_data 中
    assert result.universe_size == 1
    assert result.error != "" or result.trading_days == 0


def test_backtest_metrics_calc():
    """绩效指标计算应合理。"""
    kline_data = {"600001": _build_uptrend_kline("600001")}
    collector = MockCollector(kline_data)
    engine = BacktestEngine(collector)
    config = BacktestConfig(
        strategy_id="strong_pullback",
        symbols=["600001"],
        initial_capital=1_000_000,
        risk_config=RiskConfig(max_holdings=5),
    )

    import asyncio
    result = asyncio.run(engine.run(config))

    m = result.metrics
    assert m["initial_capital"] == 1_000_000
    assert isinstance(m["total_return_pct"], float)
    assert isinstance(m["max_drawdown_pct"], float)
    assert m["max_drawdown_pct"] >= 0  # 回撤不可能为负
    assert isinstance(m["win_rate_pct"], float)
    assert 0 <= m["win_rate_pct"] <= 100


def test_backtest_equity_curve_structure():
    """权益曲线每个点应包含必要字段。"""
    kline_data = {"600001": _build_uptrend_kline("600001")}
    collector = MockCollector(kline_data)
    engine = BacktestEngine(collector)
    config = BacktestConfig(
        strategy_id="strong_pullback",
        symbols=["600001"],
        risk_config=RiskConfig(max_holdings=5),
    )

    import asyncio
    result = asyncio.run(engine.run(config))

    for point in result.equity_curve:
        assert "date" in point
        assert "equity" in point
        assert "cash" in point
        assert "holdings_value" in point
        assert "positions" in point
        assert point["equity"] == point["cash"] + point["holdings_value"]
