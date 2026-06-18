import logging
import math
from typing import Optional

import pandas as pd

from src.config import Settings
from src.data.sources.base import DataSource

logger = logging.getLogger(__name__)

DEFAULT_INDICATORS = [
    "macd",
    "rsi",
    "sma_5",
    "sma_10",
    "sma_20",
    "sma_60",
    "sma_120",
    "ema_12",
    "ema_20",
    "ema_60",
    "bollinger",
    "kdj",
    "cci",
    "wr",
    "atr",
    "obv",
    "volume_ratio",
    "change_pct",
    "volatility_20",
    "trend_gap_20",
]


class IndicatorSource(DataSource):
    """Compute technical indicators from OHLCV data."""

    name = "indicators"

    def __init__(self, settings: Settings):
        pass

    async def get_quote(self, symbol: str) -> None:
        return None  # Not applicable

    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 60) -> None:
        return None  # Not applicable

    async def get_fundamentals(self, symbol: str) -> None:
        return None  # Not applicable

    def compute(
        self,
        ohlcv: pd.DataFrame,
        indicators: list[str] = None,
    ) -> dict:
        """Compute specified indicators on OHLCV DataFrame.

        Available indicators: macd, rsi, moving averages, bollinger, kdj,
        cci, wr, atr, obv, volume ratio, volatility, trend gap.
        """
        if ohlcv.empty or len(ohlcv) < 30:
            return {}

        indicators = indicators or DEFAULT_INDICATORS
        result = {}
        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        volume = ohlcv["volume"]

        def add(key: str, value) -> None:
            try:
                val = float(value)
            except (TypeError, ValueError):
                return
            if math.isfinite(val):
                result[key] = round(val, 4)

        if "macd" in indicators:
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema12 - ema26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            add("macd", macd_line.iloc[-1])
            add("macd_signal", signal_line.iloc[-1])
            add("macd_hist", macd_line.iloc[-1] - signal_line.iloc[-1])

        if "rsi" in indicators:
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = (-delta).where(delta < 0, 0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            add("rsi", rsi.iloc[-1])

        for window in (5, 10, 20, 60, 120):
            key = f"sma_{window}"
            if key in indicators and len(close) >= window:
                add(key, close.rolling(window=window).mean().iloc[-1])

        for span in (12, 20, 60):
            key = f"ema_{span}"
            if key in indicators:
                add(key, close.ewm(span=span, adjust=False).mean().iloc[-1])

        if "bollinger" in indicators:
            sma20 = close.rolling(window=20).mean()
            std20 = close.rolling(window=20).std()
            add("bb_upper", (sma20 + 2 * std20).iloc[-1])
            add("bb_middle", sma20.iloc[-1])
            add("bb_lower", (sma20 - 2 * std20).iloc[-1])

        if "kdj" in indicators:
            low_9 = low.rolling(window=9).min()
            high_9 = high.rolling(window=9).max()
            rsv = (close - low_9) / (high_9 - low_9) * 100
            k = rsv.ewm(com=2, adjust=False).mean()
            d = k.ewm(com=2, adjust=False).mean()
            add("kdj_k", k.iloc[-1])
            add("kdj_d", d.iloc[-1])
            add("kdj_j", 3 * k.iloc[-1] - 2 * d.iloc[-1])

        if "cci" in indicators:
            tp = (high + low + close) / 3
            ma = tp.rolling(window=20).mean()
            md = (tp - ma).abs().rolling(window=20).mean()
            cci = (tp - ma) / (0.015 * md)
            add("cci", cci.iloc[-1])

        if "wr" in indicators:
            high_14 = high.rolling(window=14).max()
            low_14 = low.rolling(window=14).min()
            wr = (high_14 - close) / (high_14 - low_14) * 100
            add("wr", wr.iloc[-1])

        if "atr" in indicators:
            prev_close = close.shift(1)
            tr = pd.concat(
                [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
                axis=1,
            ).max(axis=1)
            add("atr", tr.rolling(window=14).mean().iloc[-1])

        if "obv" in indicators:
            direction = close.diff().fillna(0).apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
            add("obv", (direction * volume).cumsum().iloc[-1])

        if "volume_ratio" in indicators:
            vol_ma5 = volume.rolling(window=5).mean()
            if len(vol_ma5) > 0 and pd.notna(vol_ma5.iloc[-1]) and vol_ma5.iloc[-1] > 0:
                add("volume_ratio", volume.iloc[-1] / vol_ma5.iloc[-1])

        if "change_pct" in indicators:
            add("change_pct", close.pct_change().iloc[-1] * 100)

        if "volatility_20" in indicators:
            add("volatility_20", close.pct_change().rolling(window=20).std().iloc[-1] * (252 ** 0.5) * 100)

        if "trend_gap_20" in indicators and "sma_20" in result:
            add("trend_gap_20", (close.iloc[-1] / result["sma_20"] - 1) * 100)

        return result
