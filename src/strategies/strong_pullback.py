"""强势回踩策略。

完整链路：强势股识别 → 健康回踩 → 买点触发。

这是对 ``volume_pullback`` 的工业级升级：
- 多因子强势评分（动量+新高+均线+放量+涨停）
- 结构化回踩检测（幅度+缩量+不破MA20+整理）
- 3 种买点触发（放量突破 / MA20反弹 / 箱体突破）
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from src.strategies.base import BaseStrategy
from src.strategies.factors import compute_factors

logger = logging.getLogger(__name__)


class StrongPullbackStrategy(BaseStrategy):
    """强势回踩选股策略。"""

    id = "strong_pullback"
    name = "强势回踩"
    description = (
        "强势股评分≥5（动量+新高+均线趋势+放量+涨停），"
        "回踩幅度-15%~0%且不破MA20、缩量整理，"
        "触发放量突破/MA20反弹/箱体突破买点"
    )
    default_params = {
        # 强势股评分
        "min_strong_score": 5,
        "momentum_window": 20,
        "momentum_threshold": 1.2,
        # 回踩检测
        "pullback_max_pct": -0.15,
        "pullback_min_pct": 0.0,
        "ma_support_period": 20,
        "ma_support_tolerance": 0.02,
        "shrink_vol_window": 5,
        "consolidation_short": 3,
        "consolidation_long": 10,
        # 买点触发
        "entry_type": "any",  # breakout | ma_bounce | box | any
        "entry_volume_ratio": 1.5,
        "entry_lookback": 5,
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
        min_len = 70  # 需要 ma60 + 足够回看
        if not kline or len(kline) < min_len:
            return None

        df = pd.DataFrame(kline)
        try:
            df = compute_factors(df)
        except ValueError:
            return None

        if len(df) < min_len:
            return None

        today = df.iloc[-1]

        # 1. 强势股评分
        score_detail = self._strong_score(df, p)
        if score_detail["total"] < int(p["min_strong_score"]):
            return None

        # 2. 回踩检测
        pullback_detail = self._detect_pullback(df, p)
        if pullback_detail is None:
            return None

        # 3. 买点触发
        entry_type = str(p["entry_type"])
        entry_detail = self._detect_entry(df, p, entry_type)
        if entry_detail is None:
            return None

        return {
            "symbol": symbol,
            "name": name,
            "market": market,
            "trade_date": trade_date,
            "strategy_id": self.id,
            "strategy_name": self.name,
            "strong_score": score_detail["total"],
            "strong_score_detail": score_detail,
            "rally_pct": round(pullback_detail["rally_pct"], 2),
            "pullback_pct": round(pullback_detail["pullback_pct"], 2),
            "peak_price": round(pullback_detail["peak_price"], 2),
            "peak_date": pullback_detail["peak_date"],
            "latest_price": round(float(today["close"]), 2),
            "latest_volume": int(today["volume"]) if pd.notna(today["volume"]) else None,
            "ma20": round(float(today["ma20"]), 2) if pd.notna(today["ma20"]) else None,
            "rsi14": round(float(today["rsi14"]), 2) if pd.notna(today["rsi14"]) else None,
            "entry_type": entry_detail["type"],
            "entry_type_label": entry_detail["label"],
            "entry_volume_ratio": round(entry_detail["volume_ratio"], 2),
            "bounce_up": entry_detail["bounce_up"],
            "description": (
                f"{name}({symbol}) 强势评分{score_detail['total']}，"
                f"20日涨幅{pullback_detail['rally_pct']:.1f}%，"
                f"回踩{pullback_detail['pullback_pct']:.1f}%，"
                f"触发{entry_detail['label']}买点"
            ),
        }

    # ---- 强势股评分 ----

    @staticmethod
    def _strong_score(df: pd.DataFrame, p: dict[str, Any]) -> dict:
        """多因子强势股评分。

        注意：动量和新高检查使用 20 日峰值（high_20）而非当前收盘价，
        因为回踩后当前价可能低于 20 日前，但股票依然是"曾经强势"的。
        """
        score = 0
        detail: dict[str, Any] = {}

        today = df.iloc[-1]
        momentum_window = int(p["momentum_window"])
        momentum_threshold = float(p["momentum_threshold"])

        # 动量：high_60 / close[-20-1] > threshold（用60日峰值衡量，避免长回踩后失效）
        if len(df) > momentum_window:
            ref_close = float(df.iloc[-1 - momentum_window]["close"])
            peak = float(today["high_60"]) if pd.notna(today["high_60"]) else float(today["close"])
            momentum = peak / ref_close if ref_close > 0 else 0
            passed = momentum > momentum_threshold
            detail["momentum"] = {"passed": passed, "value": round(momentum, 3)}
            if passed:
                score += 2

        # 新高：high_20 >= high_60（近20日内创过60日新高）
        if pd.notna(today["high_60"]):
            passed = float(today["high_20"]) >= float(today["high_60"])
            detail["new_high"] = {"passed": passed}
            if passed:
                score += 2

        # 均线趋势：ma5 > ma10 > ma20
        if pd.notna(today["ma5"]) and pd.notna(today["ma10"]) and pd.notna(today["ma20"]):
            passed = (
                float(today["ma5"]) > float(today["ma10"]) > float(today["ma20"])
            )
            detail["ma_trend"] = {"passed": passed}
            if passed:
                score += 2

        # 放量突破：vol[-5:].mean() > vol[-20:].mean()
        if len(df) >= 20:
            recent_vol = float(df["volume"].iloc[-5:].mean())
            base_vol = float(df["volume"].iloc[-20:].mean())
            passed = recent_vol > base_vol and base_vol > 0
            detail["volume_expansion"] = {"passed": passed}
            if passed:
                score += 1

        # 近10日涨停过
        recent_10 = df.iloc[-10:]
        has_limit = bool(recent_10["is_limit_up"].any()) if "is_limit_up" in recent_10 else False
        detail["limit_up_recent"] = {"passed": has_limit}
        if has_limit:
            score += 1

        detail["total"] = score
        return detail

    # ---- 回踩检测 ----

    @staticmethod
    def _detect_pullback(df: pd.DataFrame, p: dict[str, Any]) -> Optional[dict]:
        """健康回踩检测。"""
        today = df.iloc[-1]
        ma_period = int(p["ma_support_period"])
        ma_col = f"ma{ma_period}"
        if ma_col not in df.columns or pd.isna(today[ma_col]):
            return None

        high_20 = today["high_20"]
        if pd.isna(high_20) or float(high_20) <= 0:
            return None

        close = float(today["close"])
        high_20_val = float(high_20)

        # 回调幅度
        pullback_pct = (close - high_20_val) / high_20_val
        if not (float(p["pullback_max_pct"]) <= pullback_pct < float(p["pullback_min_pct"])):
            return None

        # 不破 MA20（带容差）
        ma_val = float(today[ma_col])
        if close < ma_val * (1 - float(p["ma_support_tolerance"])):
            return None

        # 缩量：回踩期间（不含今日）均量 < 上涨期间均量
        # 回踩段 = high_20峰值之后、今日之前
        high_20_idx = df["high"].iloc[-20:].idxmax()
        pullback_segment = df.iloc[high_20_idx + 1: -1]  # 不含今日
        rally_segment = df.iloc[max(0, high_20_idx - 20): high_20_idx + 1]
        if len(pullback_segment) == 0 or len(rally_segment) == 0:
            return None
        pullback_avg_vol = float(pullback_segment["volume"].mean())
        rally_avg_vol = float(rally_segment["volume"].mean())
        if rally_avg_vol <= 0:
            return None
        if pullback_avg_vol >= rally_avg_vol:
            return None

        # 整理结构：近3日（不含今日）最高 ≤ 近10日（不含今日）最高
        short_w = int(p["consolidation_short"])
        long_w = int(p["consolidation_long"])
        if len(df) >= long_w + 1:
            recent_high_short = float(df["close"].iloc[-(short_w + 1):-1].max())
            recent_high_long = float(df["close"].iloc[-(long_w + 1):-1].max())
            if recent_high_short > recent_high_long:
                return None

        # 计算上涨幅度（20日前收盘 → 20日最高）
        if len(df) > 20:
            ref_close = float(df.iloc[-21]["close"])
            rally_pct = (high_20_val / ref_close - 1) * 100 if ref_close > 0 else 0
        else:
            rally_pct = 0

        # 找峰值日期
        peak_idx = df["high"].iloc[-20:].idxmax()
        peak_date = str(df.iloc[peak_idx]["date"])

        return {
            "pullback_pct": pullback_pct * 100,
            "rally_pct": rally_pct,
            "peak_price": high_20_val,
            "peak_date": peak_date,
        }

    # ---- 买点触发 ----

    @staticmethod
    def _detect_entry(
        df: pd.DataFrame, p: dict[str, Any], entry_type: str
    ) -> Optional[dict]:
        """买点触发检测，支持 3 种类型。"""
        lookback = int(p["entry_lookback"])
        vol_ratio_threshold = float(p["entry_volume_ratio"])

        today = df.iloc[-1]
        today_close = float(today["close"])
        today_open = float(today["open"])
        today_vol = float(today["volume"])
        vol_ma5 = today["vol_ma5"]
        vol_ratio = today_vol / float(vol_ma5) if pd.notna(vol_ma5) and float(vol_ma5) > 0 else 0
        bounce_up = today_close > today_open

        if entry_type in ("breakout", "any"):
            # 买点A：放量突破短期高点
            if len(df) > lookback:
                recent_high = float(df["high"].iloc[-(lookback + 1):-1].max())
                if (
                    today_close > recent_high
                    and vol_ratio >= vol_ratio_threshold
                    and bounce_up
                ):
                    return {
                        "type": "breakout",
                        "label": "放量突破",
                        "volume_ratio": vol_ratio,
                        "bounce_up": bounce_up,
                    }

        if entry_type in ("ma_bounce", "any"):
            # 买点B：MA20支撑反弹（近3日触及MA20后今日收阳放量）
            ma20 = today["ma20"]
            if pd.notna(ma20) and len(df) >= 4:
                ma20_val = float(ma20)
                recent_3 = df.iloc[-4:-1]
                touched_ma20 = any(
                    float(row["low"]) <= ma20_val * 1.01 for _, row in recent_3.iterrows()
                )
                if touched_ma20 and bounce_up and vol_ratio >= vol_ratio_threshold:
                    return {
                        "type": "ma_bounce",
                        "label": "MA20反弹",
                        "volume_ratio": vol_ratio,
                        "bounce_up": bounce_up,
                    }

        if entry_type in ("box", "any"):
            # 买点C：箱体突破（近10日价格在箱体内震荡，今日突破上沿）
            if len(df) >= 11:
                box_data = df.iloc[-11:-1]
                box_high = float(box_data["high"].max())
                box_low = float(box_data["low"].min())
                box_range = box_high - box_low
                # 箱体幅度不超过 15%
                if box_range > 0 and box_low > 0 and box_range / box_low < 0.15:
                    if today_close > box_high and vol_ratio >= vol_ratio_threshold:
                        return {
                            "type": "box",
                            "label": "箱体突破",
                            "volume_ratio": vol_ratio,
                            "bounce_up": bounce_up,
                        }

        return None
