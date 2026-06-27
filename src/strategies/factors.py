"""因子层：从 OHLCV K 线计算完整技术指标序列。

与 ``IndicatorSource`` 不同，这里返回完整序列（DataFrame 列），
供策略检测和回测引擎在任意历史日期切片使用。
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def compute_factors(df: pd.DataFrame) -> pd.DataFrame:
    """在 OHLCV DataFrame 上增量计算技术因子列。

    输入要求列：date, open, high, low, close, volume。
    返回的 DataFrame 在原列基础上新增因子列，按 date 升序。

    新增列：
    - ma5 / ma10 / ma20 / ma60
    - atr14
    - rsi14
    - vol_ma5
    - high_20 / high_60  (滚动最高价)
    - low_20             (滚动最低价)
    - pct_change         (日收益率)
    - is_limit_up        (涨停标记)
    - is_limit_down      (跌停标记)
    """
    if df.empty:
        return df

    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        raise ValueError(f"K线数据缺少必要列: {required - set(df.columns)}")

    df = df.sort_values("date").reset_index(drop=True).copy()
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 移动平均线
    for w in (5, 10, 20, 60):
        df[f"ma{w}"] = close.rolling(window=w).mean()

    # 成交量均线
    df["vol_ma5"] = volume.rolling(window=5).mean()

    # 滚动最高/最低价
    df["high_20"] = high.rolling(window=20).max()
    df["high_60"] = high.rolling(window=60).max()
    df["low_20"] = low.rolling(window=20).min()

    # 日收益率
    df["pct_change"] = close.pct_change()

    # ATR14
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    df["atr14"] = tr.rolling(window=14).mean()

    # RSI14
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    df["rsi14"] = 100 - (100 / (1 + rs))

    # 涨跌停标记（基于前日收盘价）
    prev_close_shifted = close.shift(1)
    change_ratio = (close / prev_close_shifted - 1.0)
    # 主板 10%，创业板/科创板 20%，北交所 30%（简化：统一用 9.5% / 19.5% 阈值）
    df["_change_ratio"] = change_ratio
    df["is_limit_up"] = change_ratio >= 0.095
    df["is_limit_down"] = change_ratio <= -0.095

    return df


def slice_up_to(df: pd.DataFrame, date: str) -> pd.DataFrame:
    """返回 date 当日及之前的所有行（用于回测时按日期切片）。"""
    return df[df["date"] <= date].reset_index(drop=True)
