"""因子层计算单元测试。"""

from datetime import date, timedelta

import pandas as pd

from src.strategies.factors import compute_factors, slice_up_to


def _day_str(offset: int) -> str:
    return (date(2024, 1, 1) + timedelta(days=offset)).strftime("%Y-%m-%d")


def _build_ohlcv(n: int = 80) -> list[dict]:
    """构造 n 天的 OHLCV 数据。"""
    rows = []
    for i in range(n):
        close = 10.0 + i * 0.1
        rows.append({
            "date": _day_str(i),
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": 10000 + i * 100,
            "turnover": close * (10000 + i * 100),
            "change_pct": 0.0,
        })
    return rows


def test_compute_factors_basic():
    df = pd.DataFrame(_build_ohlcv(80))
    df = compute_factors(df)
    assert "ma5" in df.columns
    assert "ma10" in df.columns
    assert "ma20" in df.columns
    assert "ma60" in df.columns
    assert "atr14" in df.columns
    assert "rsi14" in df.columns
    assert "vol_ma5" in df.columns
    assert "high_20" in df.columns
    assert "high_60" in df.columns
    assert "low_20" in df.columns
    assert "pct_change" in df.columns
    assert "is_limit_up" in df.columns
    assert "is_limit_down" in df.columns


def test_compute_factors_ma_values():
    df = pd.DataFrame(_build_ohlcv(20))
    df = compute_factors(df)
    # ma5 第5行才有值
    assert pd.isna(df["ma5"].iloc[0])
    assert pd.notna(df["ma5"].iloc[4])
    # ma5 = 最近5天close均值
    expected_ma5 = df["close"].iloc[:5].mean()
    assert abs(df["ma5"].iloc[4] - expected_ma5) < 0.01


def test_compute_factors_high_20():
    df = pd.DataFrame(_build_ohlcv(25))
    df = compute_factors(df)
    # high_20 是滚动20日最高价
    assert pd.notna(df["high_20"].iloc[19])
    expected = df["high"].iloc[:20].max()
    assert abs(df["high_20"].iloc[19] - expected) < 0.01


def test_compute_factors_limit_up():
    rows = _build_ohlcv(30)
    # 第25天涨停（+10%）
    prev_close = rows[24]["close"]
    rows[25]["close"] = round(prev_close * 1.10, 3)
    rows[25]["high"] = round(prev_close * 1.10, 3)
    df = pd.DataFrame(rows)
    df = compute_factors(df)
    assert df["is_limit_up"].iloc[25] == True  # noqa: E712
    assert df["is_limit_up"].iloc[24] == False  # noqa: E712


def test_compute_factors_insufficient_data():
    df = pd.DataFrame(_build_ohlcv(5))
    df = compute_factors(df)
    # 数据少但仍应返回（ma60全NaN）
    assert len(df) == 5
    assert df["ma5"].isna().all() or pd.notna(df["ma5"].iloc[4])


def test_slice_up_to():
    df = pd.DataFrame(_build_ohlcv(30))
    df = compute_factors(df)
    sliced = slice_up_to(df, _day_str(10))
    assert len(sliced) == 11  # 0..10
    assert sliced["date"].iloc[-1] == _day_str(10)


def test_compute_factors_sorted():
    rows = _build_ohlcv(30)
    rows.reverse()  # 打乱顺序
    df = pd.DataFrame(rows)
    df = compute_factors(df)
    # 应按 date 升序排列
    assert df["date"].iloc[0] < df["date"].iloc[-1]


def test_compute_factors_missing_columns():
    import pytest
    df = pd.DataFrame({"date": ["2024-01-01"], "close": [10.0]})
    with pytest.raises(ValueError):
        compute_factors(df)
