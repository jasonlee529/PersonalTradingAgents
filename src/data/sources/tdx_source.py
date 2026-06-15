"""
通达信 (TDX) 数据源 - 基于 mootdx 库实现
需要安装: pip install mootdx
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.data.sources.base import DataSource

logger = logging.getLogger(__name__)


class TdxSource(DataSource):
    """通达信行情数据源，基于 mootdx 库。"""

    name = "tdx"

    def __init__(self):
        self._client = None

    def _get_client(self):
        """延迟初始化 mootdx 客户端"""
        if self._client is None:
            try:
                from mootdx import Tdx
                self._client = Tdx()
            except ImportError:
                logger.warning("mootdx 未安装，请执行: pip install mootdx")
                return None
            except Exception as e:
                logger.warning("mootdx 初始化失败: %s", e)
                return None
        return self._client

    async def get_quote(self, symbol: str) -> Optional[dict]:
        """获取实时行情"""
        client = self._get_client()
        if not client:
            return None

        try:
            code = symbol.zfill(6)
            market = 1 if code.startswith("6") else 0  # 1=上海, 0=深圳
            df = await asyncio.to_thread(client.security_bars, market=market, category=0, code=code, start=0, count=1)
            if df is None or df.empty:
                return None
            row = df.iloc[-1]
            return {
                "symbol": code,
                "name": str(row.get("name", "")),
                "price": float(row.get("close", 0)),
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "prev_close": float(row.get("close", 0)),  # mootdx 不提供 prev_close
                "volume": int(float(row.get("vol", 0))),
                "turnover": float(row.get("amount", 0)),
                "change_pct": 0.0,  # 需要计算
                "source": self.name,
            }
        except Exception as e:
            logger.warning("Tdx quote failed for %s: %s", symbol, e)
            return None

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        """获取 K 线数据"""
        client = self._get_client()
        if not client:
            return None

        try:
            code = symbol.zfill(6)
            market = 1 if code.startswith("6") else 0

            # period 映射到 mootdx category
            category_map = {
                "1d": 0, "day": 0, "daily": 0,
                "1w": 1, "week": 1,
                "1M": 2, "month": 2,
                "5min": 3,
                "15min": 4,
                "30min": 5,
                "1h": 6, "60min": 6,
                "1m": 8, "1min": 8,
            }
            category = category_map.get(period.lower(), 0)

            df = await asyncio.to_thread(
                client.security_bars,
                market=market,
                category=category,
                code=code,
                start=0,
                count=limit
            )
            if df is None or df.empty:
                return None

            records = []
            for _, row in df.iterrows():
                records.append({
                    "symbol": code,
                    "date": str(row.get("date", "")),
                    "open": float(row.get("open", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "close": float(row.get("close", 0)),
                    "volume": int(float(row.get("vol", 0))),
                    "turnover": float(row.get("amount", 0)),
                })
            return records[-limit:] if records else None
        except Exception as e:
            logger.warning("Tdx kline failed for %s: %s", symbol, e)
            return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        """获取基本面数据（通过财务指标接口）"""
        client = self._get_client()
        if not client:
            return None

        try:
            code = symbol.zfill(6)
            market = 1 if code.startswith("6") else 0
            df = await asyncio.to_thread(client.finance, market=market, symbol=code)
            if df is None or df.empty:
                return None
            row = df.iloc[-1]
            return {
                "symbol": code,
                "pe_ttm": float(row.get("PE", 0)) if "PE" in row else None,
                "pb": float(row.get("PB", 0)) if "PB" in row else None,
                "mcap": float(row.get("MCAP", 0)) if "MCAP" in row else None,  # 总市值
                "float_mcap": float(row.get("FCAP", 0)) if "FCAP" in row else None,  # 流通市值
                "source": self.name,
            }
        except Exception as e:
            logger.warning("Tdx fundamentals failed for %s: %s", symbol, e)
            return None

    async def get_market_indices(self) -> Optional[list[dict]]:
        """获取主要指数"""
        client = self._get_client()
        if not client:
            return None

        try:
            # 主要指数列表
            indices = [
                ("1", "000001"),  # 上证指数
                ("0", "399001"),  # 深证成指
                ("0", "399006"),  # 创业板指
                ("1", "000688"),  # 科创50
                ("1", "000016"),  # 上证50
                ("0", "399005"),  # 中小板指
            ]
            results = []
            for market, code in indices:
                market = int(market)
                df = await asyncio.to_thread(
                    client.security_bars,
                    market=market,
                    category=0,
                    code=code,
                    start=0,
                    count=1
                )
                if df is not None and not df.empty:
                    row = df.iloc[-1]
                    results.append({
                        "symbol": code,
                        "name": str(row.get("name", "")),
                        "price": float(row.get("close", 0)),
                        "change_pct": 0.0,  # 需要计算
                        "volume": int(float(row.get("vol", 0))),
                        "source": self.name,
                    })
            return results if results else None
        except Exception as e:
            logger.warning("Tdx market indices failed: %s", e)
            return None

    async def get_limit_up_stocks(
        self, trade_date: str = "", market: str = "all"
    ) -> Optional[list[dict]]:
        """获取涨停池数据"""
        client = self._get_client()
        if not client:
            return None

        try:
            # 使用 mootdx 的涨停股接口
            # market 参数: 0=全部, 1=上海, 2=深圳
            market_map = {"all": 0, "sh": 1, "sz": 2}
            mkt = market_map.get(market.lower(), 0)

            df = await asyncio.to_thread(
                client.limit_list,
                market=mkt,
                date=trade_date.replace("-", "") if trade_date else datetime.now().strftime("%Y%m%d")
            )
            if df is None or df.empty:
                return None

            items = []
            for _, row in df.iterrows():
                code = str(row.get("code", "")).zfill(6)
                if not code or code == "000000":
                    continue
                items.append({
                    "symbol": code,
                    "name": str(row.get("name", "") or ""),
                    "market": "sh" if code.startswith("6") else "sz",
                    "trade_date": trade_date or datetime.now().strftime("%Y-%m-%d"),
                    "price": float(row.get("close", 0)) if "close" in row else None,
                    "change_pct": float(row.get("pchange", 0)) if "pchange" in row else None,
                    "volume": None,
                    "turnover": None,
                    "turnover_rate": None,
                    "first_limit_up_time": None,
                    "last_limit_up_time": None,
                    "seal_amount": None,
                    "consecutive_days": int(row.get("days", 0)) if "days" in row else None,
                    "reason": str(row.get("reason", "") or "") if "reason" in row else "",
                    "source": self.name,
                })
            return items if items else None
        except Exception as e:
            logger.warning("Tdx limit_up_stocks failed for %s: %s", trade_date, e)
            return None

    async def get_news(self, symbol: str = "", start_date: str = "", end_date: str = "", limit: int = 20) -> Optional[list[dict]]:
        """获取股票新闻"""
        client = self._get_client()
        if not client:
            return None

        try:
            # mootdx 提供新闻接口
            articles = await asyncio.to_thread(client.news, symbol=symbol, limit=limit)
            if articles is None:
                return None

            items = []
            for _, row in articles.iterrows():
                items.append({
                    "title": str(row.get("title", "")),
                    "url": str(row.get("url", "")),
                    "datetime": str(row.get("datetime", "")),
                    "source": self.name,
                })
            return items if items else None
        except Exception as e:
            logger.warning("Tdx news failed: %s", e)
            return None

    async def health_check(self) -> bool:
        """检查数据源是否可用"""
        client = self._get_client()
        if not client:
            return False
        try:
            # 尝试获取一个简单数据来验证连接
            df = await asyncio.to_thread(
                client.security_bars,
                market=1,
                category=0,
                code="000001",
                start=0,
                count=1
            )
            return df is not None and not df.empty
        except Exception as e:
            logger.warning("Tdx health check failed: %s", e)
            return False
