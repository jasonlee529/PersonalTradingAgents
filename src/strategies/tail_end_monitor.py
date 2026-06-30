"""尾盘策略监控器。

在尾盘时段（14:30后）筛选符合多维度条件的股票：
- 换手率、市值、量比范围过滤
- 前20个交易日内有过涨停
- 14:30到当前的涨幅在指定范围
- 全天股价在均价线（VWAP）之上
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _is_mainboard(symbol: str, name: str) -> bool:
    """判断是否为主板股票（排除ST、创业板、科创板、北交所）。"""
    if "ST" in name.upper():
        return False
    # 沪市主板: 60开头
    if symbol.startswith("60"):
        return True
    # 深市主板: 00开头
    if symbol.startswith("00"):
        return True
    # 排除: 创业板(300/301), 科创板(688), 北交所(4/8/9)
    return False


def _has_limit_up_in_days(kline: list[dict], days: int = 20) -> tuple[bool, str]:
    """检查最近N个交易日内是否有涨停。

    Returns:
        (是否涨停, 最近涨停日期)
    """
    if not kline or len(kline) < 2:
        return False, ""

    recent = kline[-days:] if len(kline) >= days else kline
    for i in range(len(recent) - 1, 0, -1):
        close = float(recent[i].get("close", 0))
        prev_close = float(recent[i - 1].get("close", 0))
        if prev_close > 0:
            change_ratio = (close / prev_close) - 1.0
            if change_ratio >= 0.095:
                return True, recent[i].get("date", "")
    return False, ""


def _check_intraday_conditions(
    minute_klines: list[dict],
) -> tuple[Optional[float], bool]:
    """检查日内条件：14:30后涨幅、全天在VWAP之上。

    Args:
        minute_klines: 1分钟K线数据列表

    Returns:
        (14:30后涨幅%, 是否全天在VWAP之上)
    """
    if not minute_klines or len(minute_klines) < 10:
        return None, False

    # 找到14:30对应的K线索引
    idx_1430 = None
    for i, k in enumerate(minute_klines):
        time_str = k.get("date", "")
        # 格式: "2026-06-30 14:30" 或 "2026-06-30 14:30:00"
        if "14:30" in time_str and "14:30:" not in time_str:
            idx_1430 = i
            break
        if time_str.endswith("14:30"):
            idx_1430 = i
            break

    # 计算14:30后涨幅
    change_since_1430 = None
    if idx_1430 is not None and idx_1430 < len(minute_klines):
        price_at_1430 = float(minute_klines[idx_1430].get("close", 0))
        latest_price = float(minute_klines[-1].get("close", 0))
        if price_at_1430 > 0:
            change_since_1430 = round(
                ((latest_price / price_at_1430) - 1.0) * 100, 2
            )

    # 检查全天是否在VWAP之上
    # VWAP = 累计成交额 / 累计成交量
    above_vwap = True
    cum_turnover = 0.0
    cum_volume = 0
    for k in minute_klines:
        vol = float(k.get("volume", 0))
        close = float(k.get("close", 0))
        # 估算成交额 = 成交量 * (high+low+close)/3
        high = float(k.get("high", 0))
        low = float(k.get("low", 0))
        avg_price = (high + low + close) / 3 if (high + low + close) > 0 else close
        cum_turnover += vol * avg_price
        cum_volume += vol
        if cum_volume > 0:
            vwap = cum_turnover / cum_volume
            if close < vwap:
                above_vwap = False
                break

    return change_since_1430, above_vwap


class TailEndMonitor:
    """尾盘策略监控器。"""

    def __init__(self, collector):
        self.collector = collector

    async def scan(
        self,
        turnover_min: float = 6.0,
        turnover_max: float = 15.0,
        mcap_min: float = 50.0,
        mcap_max: float = 300.0,
        change_min: float = 3.0,
        change_max: float = 6.0,
        vol_ratio_min: float = 2.0,
        vol_ratio_max: float = 5.0,
        q: str = "",
    ) -> tuple[list[dict], str]:
        """执行尾盘扫描。

        Returns:
            (结果列表, 错误信息)
        """
        trade_date = datetime.now().strftime("%Y-%m-%d")

        # Step 1: 获取全市场数据
        rows, err = await self.collector.get_market_list(trade_date=trade_date)
        if rows is None:
            return [], err or "无法获取全市场数据"

        # Step 2: 基础条件过滤
        candidates = []
        for stock in rows:
            symbol = str(stock.get("symbol", ""))
            name = str(stock.get("name", ""))

            # 主板过滤
            if not _is_mainboard(symbol, name):
                continue

            # 换手率过滤
            turnover_rate = stock.get("turnover_rate")
            if turnover_rate is None:
                continue
            turnover_rate = float(turnover_rate)
            if not (turnover_min <= turnover_rate <= turnover_max):
                continue

            # 市值过滤（eastmarket 返回的 total_market_cap 单位为元）
            mcap = stock.get("total_market_cap")
            if mcap is None or mcap <= 0:
                continue
            mcap_yi = float(mcap) / 100000000  # 转为亿
            if not (mcap_min <= mcap_yi <= mcap_max):
                continue

            # 量比过滤
            vol_ratio = stock.get("volume_ratio")
            if vol_ratio is None:
                continue
            vol_ratio = float(vol_ratio)
            if not (vol_ratio_min <= vol_ratio <= vol_ratio_max):
                continue

            # 搜索关键字过滤
            if q:
                needle = q.strip().lower()
                if needle not in symbol.lower() and needle not in name.lower():
                    continue

            stock["_mcap_yi"] = round(mcap_yi, 2)
            stock["_turnover_rate"] = turnover_rate
            stock["_vol_ratio"] = vol_ratio
            candidates.append(stock)

        if not candidates:
            return [], ""

        logger.info("尾盘扫描: 基础过滤后 %d 只候选股", len(candidates))

        # Step 3: 批量获取日K线，检查近20日涨停
        semaphore_daily = asyncio.Semaphore(10)

        async def _check_limit_up(stock: dict) -> Optional[dict]:
            async with semaphore_daily:
                try:
                    symbol = stock.get("symbol", "")
                    kline = await self.collector.get_kline(symbol, period="1d", limit=30)
                    if not kline or len(kline) < 5:
                        return None
                    has_lu, lu_date = _has_limit_up_in_days(kline, days=20)
                    if not has_lu:
                        return None
                    stock["_limit_up_date"] = lu_date
                    stock["_daily_kline"] = kline
                    return stock
                except Exception as e:
                    logger.debug("尾盘扫描 涨停检查 %s 失败: %s", stock.get("symbol"), e)
                    return None

        tasks = [_check_limit_up(s) for s in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        limit_up_candidates = [r for r in results if isinstance(r, dict)]

        if not limit_up_candidates:
            return [], ""

        logger.info("尾盘扫描: 涨停过滤后 %d 只", len(limit_up_candidates))

        # Step 4: 获取分钟K线，检查日内条件
        semaphore_intra = asyncio.Semaphore(5)

        async def _check_intraday(stock: dict) -> Optional[dict]:
            async with semaphore_intra:
                try:
                    symbol = stock.get("symbol", "")
                    minute_klines = await self._fetch_minute_kline(symbol)
                    if not minute_klines:
                        return None

                    change_1430, above_vwap = _check_intraday_conditions(minute_klines)

                    # 14:30后涨幅过滤
                    if change_1430 is None:
                        return None
                    if not (change_min <= change_1430 <= change_max):
                        return None

                    # 全天在VWAP之上
                    if not above_vwap:
                        return None

                    stock["_change_since_1430"] = change_1430
                    stock["_above_vwap"] = above_vwap

                    # 取最近3天K线
                    daily_kline = stock.get("_daily_kline", [])
                    stock["_kline_3d"] = daily_kline[-3:] if len(daily_kline) >= 3 else daily_kline

                    return stock
                except Exception as e:
                    logger.debug("尾盘扫描 日内检查 %s 失败: %s", stock.get("symbol"), e)
                    return None

        tasks2 = [_check_intraday(s) for s in limit_up_candidates]
        results2 = await asyncio.gather(*tasks2, return_exceptions=True)
        matched = [r for r in results2 if isinstance(r, dict)]

        # 整理输出
        output = []
        for stock in matched:
            symbol = stock.get("symbol", "")
            market = self.collector._infer_market(symbol)
            output.append({
                "symbol": symbol,
                "name": stock.get("name", ""),
                "market": market,
                "price": float(stock.get("price", 0)),
                "change_pct": float(stock.get("change_pct", 0)),
                "turnover_rate": stock.get("_turnover_rate"),
                "total_market_cap": stock.get("_mcap_yi"),
                "volume_ratio": stock.get("_vol_ratio"),
                "change_since_1430": stock.get("_change_since_1430"),
                "above_vwap": stock.get("_above_vwap", False),
                "recent_limit_up": True,
                "limit_up_date": stock.get("_limit_up_date", ""),
                "kline_3d": stock.get("_kline_3d", []),
            })

        # 按14:30后涨幅降序排序
        output.sort(key=lambda x: float(x.get("change_since_1430", 0)), reverse=True)
        logger.info("尾盘扫描完成: 命中 %d 只", len(output))
        return output, ""

    async def _fetch_minute_kline(self, symbol: str) -> Optional[list[dict]]:
        """获取当日1分钟K线数据（eastmoney push2his API）。"""
        try:
            code = str(symbol).zfill(6)
            market_code = 1 if code.startswith("6") else 0
            secid = f"{market_code}.{code}"
            today = datetime.now().strftime("%Y%m%d")

            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                "secid": secid,
                "klt": "1",  # 1分钟
                "fqt": "0",
                "beg": today,
                "end": today,
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            }
            r = await asyncio.to_thread(
                requests.get,
                url,
                params=params,
                headers={"User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"},
                timeout=10,
            )
            d = r.json()
            klines = d.get("data", {}).get("klines", [])
            if not klines:
                return None

            records = []
            for line in klines:
                parts = line.split(",")
                if len(parts) < 6:
                    continue
                records.append({
                    "date": parts[0],
                    "open": float(parts[1]) if parts[1] else 0.0,
                    "close": float(parts[2]) if parts[2] else 0.0,
                    "high": float(parts[3]) if parts[3] else 0.0,
                    "low": float(parts[4]) if parts[4] else 0.0,
                    "volume": int(float(parts[5])) if parts[5] else 0,
                    "turnover": float(parts[6]) if len(parts) > 6 and parts[6] else 0.0,
                })
            return records
        except Exception as e:
            logger.debug("获取分钟K线失败 %s: %s", symbol, e)
            return None
