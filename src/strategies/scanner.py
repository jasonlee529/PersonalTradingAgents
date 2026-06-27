"""全市场策略扫描器。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from src.strategies.base import BaseStrategy
from src.strategies.registry import get_strategy

logger = logging.getLogger(__name__)


class StrategyScanner:
    """依赖 ``DataCollector`` 对全市场运行策略扫描。"""

    def __init__(self, collector):
        self.collector = collector

    async def scan(
        self,
        strategy_id: str,
        trade_date: str = "",
        market: str = "all",
        params: Optional[dict[str, Any]] = None,
        max_stocks: int = 200,
        kline_limit: int = 60,
    ) -> tuple[Optional[list[dict]], str]:
        """运行策略扫描。

        Returns:
            (matches, error_msg)
        """
        strategy = get_strategy(strategy_id)
        if strategy is None:
            return [], f"未知策略: {strategy_id}"

        effective_date = trade_date or datetime.now().strftime("%Y-%m-%d")

        rows, err = await self.collector.get_market_list(trade_date=trade_date)
        if rows is None:
            return [], err or "无法获取全市场数据"

        candidates: list[dict] = []
        for stock in rows:
            symbol = str(stock.get("symbol", ""))
            # 过滤创业板
            if symbol.startswith(("300", "301")):
                continue
            inferred = self.collector._infer_market(symbol)
            if market == "sh" and inferred != "sh":
                continue
            if market == "sz" and inferred != "sz":
                continue
            if market == "bj" and inferred != "bj":
                continue
            if not stock.get("price") or float(stock.get("price", 0)) <= 0:
                continue
            stock["market"] = inferred
            stock["trade_date"] = effective_date
            candidates.append(stock)

        # 按成交额降序，取前 max_stocks 只
        candidates.sort(key=lambda x: float(x.get("turnover") or 0), reverse=True)
        candidates = candidates[:max_stocks]

        logger.info("策略 %s 开始扫描 %d 只股票...", strategy_id, len(candidates))

        semaphore = asyncio.Semaphore(10)

        async def _process(stock: dict) -> Optional[dict]:
            async with semaphore:
                try:
                    symbol = stock.get("symbol", "")
                    kline = await self.collector.get_kline(symbol, limit=kline_limit)
                    return strategy.detect(
                        symbol=symbol,
                        name=stock.get("name", ""),
                        market=stock.get("market", ""),
                        kline=kline,
                        trade_date=effective_date,
                        params=params,
                    )
                except Exception as e:  # noqa: BLE001
                    logger.debug("扫描 %s 失败: %s", stock.get("symbol"), e)
                    return None

        tasks = [_process(s) for s in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        matches: list[dict] = []
        for r in results:
            if isinstance(r, dict):
                matches.append(r)

        matches.sort(key=lambda x: float(x.get("rally_pct", 0)), reverse=True)
        logger.info("策略 %s 扫描完成，命中 %d 只", strategy_id, len(matches))
        return matches, ""
