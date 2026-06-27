"""策略基类定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseStrategy(ABC):
    """量化选股策略抽象基类。

    子类需定义 ``id``/``name``/``description``/``default_params``，
   并实现 :meth:`detect`。
    """

    id: str = ""
    name: str = ""
    description: str = ""
    default_params: dict[str, Any] = {}

    @abstractmethod
    def detect(
        self,
        symbol: str,
        name: str,
        market: str,
        kline: list[dict],
        trade_date: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict]:
        """对单只股票的 K 线数据运行策略检测。

        Args:
            symbol: 股票代码
            name: 股票名称
            market: 市场标识 (sh/sz/bj)
            kline: K 线数据列表，按日期升序，含 date/open/high/low/close/volume
            trade_date: 交易日 (YYYY-MM-DD)
            params: 策略参数覆盖

        Returns:
            命中则返回结果 dict，否则返回 None。
        """

    def merged_params(self, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        merged = dict(self.default_params)
        if params:
            merged.update(params)
        return merged
