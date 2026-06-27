"""放量回踩策略检测单元测试。"""

from datetime import date, timedelta

from src.strategies.volume_pullback import VolumePullbackStrategy


def _day_str(offset: int) -> str:
    base = date(2024, 1, 1)
    return (base + timedelta(days=offset)).strftime("%Y-%m-%d")


def _build_kline(closes: list[float], volumes: list[int], highs=None, lows=None, opens=None) -> list[dict]:
    """根据收盘价/成交量序列构造 K 线数据。

    high/low/open 缺省时由 close 推导，保证 OHLC 合理。
    """
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.98 for c in closes]
    opens = opens or [c * 0.995 for c in closes]
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


def _build_matching_kline(peak_close: float = 13.5) -> list[dict]:
    """构造一个符合"放量回踩"形态的 K 线序列。

    Args:
        peak_close: 上涨峰值收盘价（起点 10.0），决定涨幅。
    """
    # 前 20 天平稳在 10 元
    closes = [10.0] * 20
    vols = [5000] * 20
    # 上涨段 20→30: 10 → peak_close，放量
    rally_steps = 11
    for i in range(rally_steps):
        closes.append(10.0 + (peak_close - 10.0) * i / (rally_steps - 1))
        vols.append(10000 + 1000 * i)  # 10000..20000
    # 回调段 31..38：回踩 MA10、缩量
    pullback_closes = [peak_close - 0.3, peak_close - 0.9, peak_close - 1.7,
                       peak_close - 2.1, peak_close - 2.0, peak_close - 1.8,
                       peak_close - 1.6, peak_close - 1.4]
    pullback_vols = [6000, 5000, 4000, 3500, 3200, 3400, 3600, 3800]
    closes.extend(pullback_closes)
    vols.extend(pullback_vols)
    # 今日（放量、收阳）
    closes.append(peak_close - 0.9)
    vols.append(9000)

    opens = [c * 0.995 for c in closes]
    opens[-1] = closes[-1] - 0.4  # 今日开盘低于收盘 → 收阳
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.97 for c in closes]
    return _build_kline(closes, vols, highs=highs, lows=lows, opens=opens)


def test_volume_pullback_match():
    strategy = VolumePullbackStrategy()
    kline = _build_matching_kline()
    result = strategy.detect("600001", "测试股", "sh", kline, "2024-02-15")

    assert result is not None
    assert result["symbol"] == "600001"
    assert result["market"] == "sh"
    assert result["strategy_id"] == "volume_pullback"
    assert result["rally_pct"] >= 30.0
    assert result["touch_date"]  # 有回踩日期
    assert result["contraction_ratio"] <= 0.7
    assert result["expansion_ratio"] >= 1.5
    assert result["bounce_up"] is True
    assert result["latest_price"] == 12.6


def test_volume_pullback_insufficient_data():
    strategy = VolumePullbackStrategy()
    short_kline = _build_kline([10.0] * 10, [5000] * 10)
    assert strategy.detect("600002", "短数据", "sh", short_kline, "2024-02-15") is None


def test_volume_pullback_no_rally():
    """价格平稳，不满足 30% 涨幅。"""
    strategy = VolumePullbackStrategy()
    closes = [10.0] * 40
    vols = [5000] * 40
    kline = _build_kline(closes, vols)
    assert strategy.detect("600003", "平稳股", "sh", kline, "2024-02-15") is None


def test_volume_pullback_no_ma_touch():
    """急涨后浅回调，但低点始终高于 MA10（未回踩）。"""
    strategy = VolumePullbackStrategy()
    closes = [10.0] * 30
    vols = [5000] * 30
    # 急涨段 30→36: 10 → 14（40%），MA10 远低于价格
    for i in range(7):
        closes.append(10.0 + 0.6 * i)
        vols.append(15000)
    # 浅回调 37..38：价格仍远高于 MA10，低点紧凑（不触及 MA10）
    closes.extend([13.9, 13.8])
    vols.extend([5000, 5000])
    # 今日放量收阳
    closes.append(13.9)
    vols.append(12000)
    opens = [c * 0.995 for c in closes]
    opens[-1] = 13.6
    # 紧凑低点，确保不跌破 MA10
    lows = [c * 0.998 for c in closes]
    highs = [c * 1.01 for c in closes]
    kline = _build_kline(closes, vols, highs=highs, lows=lows, opens=opens)
    assert strategy.detect("600004", "未回踩", "sh", kline, "2024-02-15") is None


def test_volume_pullback_no_contraction():
    """回调过程未缩量。"""
    strategy = VolumePullbackStrategy()
    kline = _build_matching_kline()
    # 把回调段成交量抬高到与上涨段相当
    # 回调段索引 31..38
    for i in range(31, 39):
        kline[i]["volume"] = 18000
    # 今日仍放量
    kline[-1]["volume"] = 30000
    assert strategy.detect("600005", "未缩量", "sh", kline, "2024-02-15") is None


def test_volume_pullback_no_expansion():
    """今日未放量。"""
    strategy = VolumePullbackStrategy()
    kline = _build_matching_kline()
    # 今日成交量压低
    kline[-1]["volume"] = 4000
    assert strategy.detect("600006", "未放量", "sh", kline, "2024-02-15") is None


def test_volume_pullback_not_bounce_up():
    """今日放量但收阴（require_bounce_up=True 时不命中）。"""
    strategy = VolumePullbackStrategy()
    kline = _build_matching_kline()
    # 今日改成收阴：开盘高于收盘
    kline[-1]["open"] = 12.8
    kline[-1]["close"] = 12.6
    assert strategy.detect("600007", "收阴", "sh", kline, "2024-02-15") is None

    # 关闭收阳要求后命中
    result = strategy.detect("600007", "收阴", "sh", kline, "2024-02-15", params={"require_bounce_up": False})
    assert result is not None
    assert result["bounce_up"] is False


def test_volume_pullback_custom_params():
    """自定义参数（降低涨幅门槛）使原本不达标的序列命中。"""
    strategy = VolumePullbackStrategy()
    # 峰值 12.0 → 约 20% 涨幅，默认 30% 不命中
    kline = _build_matching_kline(peak_close=12.0)
    assert strategy.detect("600008", "低涨幅", "sh", kline, "2024-02-15") is None
    # 放宽到 15% 命中
    result = strategy.detect(
        "600008", "低涨幅", "sh", kline, "2024-02-15", params={"min_rally_pct": 15.0}
    )
    assert result is not None
    assert result["rally_pct"] >= 15.0


def test_registry_and_scanner_imports():
    """注册表与扫描器可正常导入。"""
    from src.strategies import list_strategies, get_strategy, StrategyScanner

    strategies = list_strategies()
    assert any(s.id == "volume_pullback" for s in strategies)
    assert get_strategy("volume_pullback") is not None
    assert get_strategy("not_exist") is None
    # 扫描器可实例化（不执行真实扫描）
    scanner = StrategyScanner(collector=object())
    assert scanner is not None
