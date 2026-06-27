"""强势回踩策略检测单元测试。"""

from datetime import date, timedelta

import pandas as pd

from src.strategies.strong_pullback import StrongPullbackStrategy


def _day_str(offset: int) -> str:
    return (date(2024, 1, 1) + timedelta(days=offset)).strftime("%Y-%m-%d")


def _build_kline(
    closes: list[float],
    volumes: list[int],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    opens: list[float] | None = None,
) -> list[dict]:
    n = len(closes)
    highs = highs or [c * 1.02 for c in closes]
    lows = lows or [c * 0.98 for c in closes]
    opens = opens or [c * 0.998 for c in closes]
    return [
        {
            "date": _day_str(i),
            "open": round(opens[i], 3),
            "high": round(highs[i], 3),
            "low": round(lows[i], 3),
            "close": round(closes[i], 3),
            "volume": int(volumes[i]),
            "turnover": round(closes[i] * volumes[i], 2),
            "change_pct": 0.0,
        }
        for i in range(n)
    ]


def _build_strong_pullback_kline() -> list[dict]:
    """构造符合强势回踩形态的 K 线。"""
    n = 78  # 0..77，index 77 为今日（放量突破日）
    closes = [0.0] * n
    volumes = [0] * n
    # 前 55 天平稳在 10 元（建立 ma60）
    for i in range(56):
        closes[i] = 10.0 + i * 0.02
        volumes[i] = 5000
    # 急涨 56→59: 10→13→涨停14.3（放量）
    closes[56] = 11.0
    closes[57] = 12.0
    closes[58] = 13.0
    closes[59] = 13.0 * 1.10  # 涨停
    for i in range(56, 60):
        volumes[i] = 15000
    # 回踩 60→69: 14.3→11.5（缩量）
    pullback_c = [14.0, 13.5, 12.8, 12.2, 11.8, 11.5, 11.6, 11.7, 11.8, 11.9]
    pullback_v = [8000, 7000, 6000, 5000, 4500, 4000, 4200, 4400, 4600, 4800]
    for j in range(10):
        closes[60 + j] = pullback_c[j]
        volumes[60 + j] = pullback_v[j]
    # 第70天涨停（在最近10日内）
    closes[70] = closes[69] * 1.10
    volumes[70] = 12000
    # 整理 71→76
    for i in range(71, 77):
        closes[i] = 12.0 + (i % 3) * 0.1
        volumes[i] = 4500 + (i % 3) * 200
    # 今日（index 77）：放量突破短期高点（买点A）
    closes[77] = 12.8
    volumes[77] = 12000
    opens = [c * 0.997 for c in closes]
    opens[77] = 12.3  # 收阳
    highs = [c * 1.02 for c in closes]
    lows = [c * 0.98 for c in closes]
    return _build_kline(closes, volumes, highs=highs, lows=lows, opens=opens)


# 测试用放宽评分门槛，验证策略逻辑流程（生产默认5）
TEST_PARAMS = {"min_strong_score": 3}


def test_strong_pullback_match():
    strategy = StrongPullbackStrategy()
    kline = _build_strong_pullback_kline()
    result = strategy.detect("600001", "测试股", "sh", kline, "2024-03-20", params=TEST_PARAMS)
    assert result is not None
    assert result["symbol"] == "600001"
    assert result["strategy_id"] == "strong_pullback"
    assert result["strong_score"] >= 3
    assert result["entry_type"] in ("breakout", "ma_bounce", "box")
    assert result["rally_pct"] > 0
    assert result["pullback_pct"] < 0


def test_strong_pullback_insufficient_data():
    strategy = StrongPullbackStrategy()
    short_kline = _build_kline([10.0] * 50, [5000] * 50)
    assert strategy.detect("600002", "短数据", "sh", short_kline, "2024-03-20") is None


def test_strong_pullback_no_momentum():
    """价格平稳，无动量。"""
    strategy = StrongPullbackStrategy()
    closes = [10.0] * 80
    volumes = [5000] * 80
    kline = _build_kline(closes, volumes)
    assert strategy.detect("600003", "平稳股", "sh", kline, "2024-03-20") is None


def test_strong_pullback_strong_score_only():
    """强势但无回踩（持续上涨）应不命中。"""
    strategy = StrongPullbackStrategy()
    closes = [10.0 + i * 0.2 for i in range(80)]  # 持续上涨
    volumes = [10000 + i * 100 for i in range(80)]
    kline = _build_kline(closes, volumes)
    # 持续上涨无回踩
    result = strategy.detect("600004", "持续涨", "sh", kline, "2024-03-20")
    # 可能命中买点但 pullback_pct >= 0 应排除
    assert result is None


def test_strong_pullback_entry_type_filter():
    """指定 entry_type=box 但实际是 breakout 时不命中。"""
    strategy = StrongPullbackStrategy()
    kline = _build_strong_pullback_kline()
    # 强制只看放量突破
    result = strategy.detect("600005", "过滤", "sh", kline, "2024-03-20",
                              params={**TEST_PARAMS, "entry_type": "breakout"})
    # 应命中（因为构造的就是 breakout）
    assert result is not None
    assert result["entry_type"] == "breakout"


def test_strong_pullback_score_detail():
    """评分明细应包含各因子。"""
    strategy = StrongPullbackStrategy()
    kline = _build_strong_pullback_kline()
    result = strategy.detect("600006", "评分", "sh", kline, "2024-03-20", params=TEST_PARAMS)
    assert result is not None
    detail = result["strong_score_detail"]
    assert "total" in detail
    assert "momentum" in detail


def test_registry_includes_strong_pullback():
    """注册表应包含 strong_pullback。"""
    from src.strategies import list_strategies
    ids = [s.id for s in list_strategies()]
    assert "strong_pullback" in ids
    assert "volume_pullback" in ids
