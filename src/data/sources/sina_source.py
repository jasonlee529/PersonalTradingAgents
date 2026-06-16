import asyncio
import json
import logging
from typing import Optional

import requests

from src.data.sources.base import DataSource
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class SinaSource(DataSource):
    """A-share kline and financial reports via Sina Finance HTTP API."""

    name = "sina"

    # Known Shanghai index codes that start with 0
    _SH_INDEX_CODES = {"000001", "000016", "000300", "000905"}

    @staticmethod
    def _get_prefix(code: str) -> str:
        if code in SinaSource._SH_INDEX_CODES or code.startswith(("6", "9")):
            return "sh"
        elif code.startswith("8"):
            return "bj"
        return "sz"

    def _fetch_kline(self, code: str, limit: int) -> list[dict]:
        prefix = self._get_prefix(code)
        url = (
            "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData"
        )
        params = {
            "symbol": f"{prefix}{code}",
            "scale": "240",
            "ma": "no",
            "datalen": str(min(limit, 800)),
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = json.loads(r.text)

        records = []
        for item in data:
            records.append({
                "date": item["day"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": int(item["volume"]),
                "turnover": 0.0,
                "amplitude": 0.0,
                "change_pct": 0.0,
                "change_amt": 0.0,
                "turnover_rate": 0.0,
            })
        return records

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        if period != "1d":
            logger.warning("Sina only supports daily kline; period=%s ignored", period)
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            records = await asyncio.to_thread(self._fetch_kline, code, limit)
            return records[-limit:] if records else None
        except Exception as e:
            logger.warning("Sina kline failed for %s: %s", code, e)
            return None

    def _fetch_financial_report(
        self, code: str, report_type: str, freq: str = "quarterly"
    ) -> list[dict]:
        _report_map = {"balance_sheet": "fzb", "cashflow": "llb", "income_statement": "lrb"}
        source_type = _report_map.get(report_type, "lrb")
        prefix = "sh" if code.startswith("6") else "sz"
        paper_code = f"{prefix}{code}"
        url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
        params = {
            "paperCode": paper_code,
            "source": source_type,
            "type": "0",
            "page": "1",
            "num": "20",
        }
        r = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=15)
        d = r.json()
        items = d.get("result", {}).get("data", {}).get(source_type, [])
        if not isinstance(items, list) or not items:
            return []
        return items

    async def get_balance_sheet(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            return await asyncio.to_thread(
                self._fetch_financial_report, code, "balance_sheet", freq
            )
        except Exception as e:
            logger.warning("Sina balance sheet failed for %s: %s", code, e)
            return None

    async def get_cashflow(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            return await asyncio.to_thread(
                self._fetch_financial_report, code, "cashflow", freq
            )
        except Exception as e:
            logger.warning("Sina cashflow failed for %s: %s", code, e)
            return None

    async def get_income_statement(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            return await asyncio.to_thread(
                self._fetch_financial_report, code, "income_statement", freq
            )
        except Exception as e:
            logger.warning("Sina income statement failed for %s: %s", code, e)
            return None

    async def get_limit_up_stocks(
        self, trade_date: str = "", market: str = "all"
    ) -> Optional[list[dict]]:
        """获取涨停股票列表，通过新浪财经涨停专题页面。"""
        try:
            # 新浪财经涨停池数据接口
            url = "https://vip.stock.finance.sina.com.cn/q/view/vML_Knowledge.php"
            params = {
                "page": "1",
                "num": "10000",
                "type": "1",  # 1=涨停
                "filter": "YSTAG",
            }
            headers = {
                "User-Agent": _UA,
                "Referer": "https://vip.stock.finance.sina.com.cn/",
            }
            r = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            r.encoding = "gb2312"
            html = r.text

            import re
            items = []
            # 解析表格数据，格式: 代码, 名称, 涨幅, 现价, 成交量, 成交额, ...
            rows = re.findall(
                r"<td[^>]*>(\d{6})</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*>([\d.]+)</td>\s*<td[^>]*>([\d.]+)</td>",
                html,
            )
            for code, name, change_pct, price in rows:
                code = code.zfill(6)
                items.append({
                    "symbol": code,
                    "name": name.strip(),
                    "market": "sh" if code.startswith("6") else "sz",
                    "trade_date": trade_date,
                    "price": float(price) if price else None,
                    "change_pct": float(change_pct) if change_pct else None,
                    "volume": None,
                    "turnover": None,
                    "turnover_rate": None,
                    "first_limit_up_time": None,
                    "last_limit_up_time": None,
                    "seal_amount": None,
                    "consecutive_days": None,
                    "reason": "",
                    "source": self.name,
                })
            return items if items else None
        except Exception as e:
            logger.warning("Sina limit-up stocks failed for %s: %s", trade_date, e)
            return None

    async def get_news(self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 20) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            prefix = self._get_prefix(code)
            url = f"https://vip.stock.finance.sina.com.cn/corp/view/vCB_AllNewsStock.php?symbol={prefix}{code}&Page=1"
            headers = {
                "User-Agent": _UA,
                "Referer": "https://finance.sina.com.cn/",
            }
            r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
            r.raise_for_status()
            r.encoding = "gb2312"
            html = r.text

            import re
            articles = []
            rows = re.findall(
                r"(\d{4}-\d{2}-\d{2})\s*(?:&nbsp;)*(\d{2}:\d{2})\s*(?:&nbsp;)*"
                r"<a[^>]+href='([^']+)'[^>]*>([^<]+)</a>",
                html,
            )
            for date_str, time_str, link, title in rows[:limit]:
                articles.append({
                    "title": title.strip(),
                    "content": "",
                    "time": f"{date_str} {time_str}",
                    "source": "新浪财经",
                    "url": link,
                })
            return articles
        except Exception as e:
            logger.warning("Sina news failed for %s: %s", code, e)
            return None

    async def get_quote(self, symbol: str) -> Optional[dict]:
        return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return None

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._fetch_kline, "000001", 1),
                timeout=10,
            )
            return True
        except Exception:
            return False
