"""放量回踩策略。

形态定义：
1. 最近 ``rally_days`` 个交易日上涨 ≥ ``min_rally_pct``%；
2. 见高点后回调，期间触及/跌破 MA{ma_period}；
3. 回调过程缩量（回调均量 ≤ 上涨均量 × contraction_ratio）；
4. 近期再次放量（今日量 ≥ 回调均量 × expansion_ratio）。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from src.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class VolumePullbackStrategy(BaseStrategy):
    """放量回踩形态选股策略。"""

    id = "volume_pullback"
    name = "放量回踩"
    description = "最近20天上涨30%以上，随后回踩MA10，回调缩量，近期再次放量"
    default_params = {
        "rally_days": 20,
        "min_rally_pct": 30.0,
        "ma_period": 10,
        "pullback_tolerance": 0.02,
        "contraction_ratio": 0.7,
        "expansion_ratio": 1.5,
        "min_pullback_days": 2,
        "require_bounce_up": True,
    }

    def detect(
        self,
        symbol: str,
        name: str,
        market: str,
        kline: list[dict],
        trade_date: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict]:
        p = self.merged_params(params)
        rally_days = int(p["rally_days"])
        min_rally_pct = float(p["min_rally_pct"])
        ma_period = int(p["ma_period"])
        pullback_tolerance = float(p["pullback_tolerance"])
        contraction_ratio = float(p["contraction_ratio"])
        expansion_ratio = float(p["expansion_ratio"])
        min_pullback_days = int(p["min_pullback_days"])
        require_bounce_up = bool(p["require_bounce_up"])

        min_len = rally_days + ma_period + min_pullback_days + 1
        if not kline or len(kline) < min_len:
            return None

        df = pd.DataFrame(kline)
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            return None

        df = df.sort_values("date").reset_index(drop=True)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        n = len(df)
        if n < min_len:
            return None

        df["ma"] = df["close"].rolling(ma_period).mean()

        # 今日为最后一根（放量日）
        today_idx = n - 1
        # 上涨窗口 = 最近 rally_days 根（含今日）
        window_start = n - rally_days
        start_close = float(df.iloc[window_start - 1]["close"])
        if start_close <= 0:
            return None

        window = df.iloc[window_start: today_idx + 1]
        peak_idx = int(window["high"].idxmax())
        peak_high = float(df.iloc[peak_idx]["high"])
        peak_date = str(df.iloc[peak_idx]["date"])

        rally_pct = (peak_high / start_close - 1) * 100
        if rally_pct < min_rally_pct:
            return None

        # 回调窗口 = peak 之后、今日之前
        pullback = df.iloc[peak_idx + 1: today_idx]
        if len(pullback) < min_pullback_days:
            return None

        # 回踩 MA 判定
        touched_ma = False
        touch_date = ""
        for j in range(peak_idx + 1, today_idx):
            ma_j = df.iloc[j]["ma"]
            if pd.isna(ma_j):
                continue
            low_j = float(df.iloc[j]["low"])
            if low_j <= float(ma_j) * (1 + pullback_tolerance):
                touched_ma = True
                touch_date = str(df.iloc[j]["date"])
                break
        if not touched_ma:
            return None

        # 缩量判定
        rally_segment = df.iloc[window_start: peak_idx + 1]
        rally_avg_vol = float(rally_segment["volume"].mean()) if len(rally_segment) else 0.0
        pullback_avg_vol = float(pullback["volume"].mean()) if len(pullback) else 0.0
        if rally_avg_vol <= 0:
            return None
        if pullback_avg_vol > rally_avg_vol * contraction_ratio:
            return None

        # 放量判定
        today_vol = float(df.iloc[today_idx]["volume"])
        today_open = float(df.iloc[today_idx]["open"])
        today_close = float(df.iloc[today_idx]["close"])
        if pullback_avg_vol <= 0:
            return None
        if today_vol < pullback_avg_vol * expansion_ratio:
            return None

        bounce_up = today_close > today_open
        if require_bounce_up and not bounce_up:
            return None

        contraction_actual = pullback_avg_vol / rally_avg_vol
        expansion_actual = today_vol / pullback_avg_vol

        return {
            "symbol": symbol,
            "name": name,
            "market": market,
            "trade_date": trade_date,
            "strategy_id": self.id,
            "strategy_name": self.name,
            "rally_pct": round(rally_pct, 2),
            "peak_price": round(peak_high, 2),
            "peak_date": peak_date,
            "ma_period": ma_period,
            "touch_date": touch_date,
            "latest_price": round(today_close, 2),
            "latest_volume": int(today_vol) if today_vol else None,
            "rally_avg_volume": int(rally_avg_vol) if rally_avg_vol else None,
            "pullback_avg_volume": int(pullback_avg_vol) if pullback_avg_vol else None,
            "contraction_ratio": round(contraction_actual, 2),
            "expansion_ratio": round(expansion_actual, 2),
            "bounce_up": bounce_up,
            "description": (
                f"{name}({symbol}) 最近{rally_days}天上涨{rally_pct:.1f}%，"
                f"回踩MA{ma_period}后缩量企稳，今日放量{'收阳' if bounce_up else ''}"
            ),
        }
