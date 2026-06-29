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

    def _fetch_index_quotes(self, symbols: list[str]) -> list[dict]:
        url = "https://hq.sinajs.cn/list=" + ",".join(symbols)
        headers = {"User-Agent": _UA, "Referer": "https://finance.sina.com.cn/"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        r.encoding = "gbk"
        records = []
        for line in r.text.splitlines():
            if not line.strip() or '"' not in line:
                continue
            symbol = line.split("=")[0].split("_")[-1]
            values = line.split('"')[1].split(",")
            if len(values) < 6 or not values[1]:
                continue
            current = float(values[1] or 0)
            prev_close = float(values[2] or 0)
            open_price = float(values[5] or 0)
            high = float(values[3] or 0)
            low = float(values[4] or 0)
            volume = int(float(values[8] or 0)) if len(values) > 8 else 0
            amount = float(values[9] or 0) if len(values) > 9 else 0.0
            change = current - prev_close if current and prev_close else 0.0
            change_pct = change / prev_close * 100 if prev_close else 0.0
            records.append({
                "symbol": symbol,
                "current": current,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
                "open": open_price,
                "high": high,
                "low": low,
                "volume": volume,
                "amount": amount,
            })
        return records

    async def get_market_indices(self) -> Optional[list[dict]]:
        indices_map = {
            "sh000001": ("000001", "上证指数"),
            "sz399001": ("399001", "深证成指"),
            "sz399006": ("399006", "创业板指"),
            "sh000688": ("000688", "科创50"),
            "sh000016": ("000016", "上证50"),
            "sh000300": ("000300", "沪深300"),
        }
        try:
            rows = await asyncio.to_thread(self._fetch_index_quotes, list(indices_map.keys()))
            by_symbol = {row.pop("symbol"): row for row in rows}
            results = []
            for symbol, (code, name) in indices_map.items():
                row = by_symbol.get(symbol)
                if not row:
                    continue
                results.append({
                    "code": code,
                    "name": name,
                    **row,
                    "amplitude": 0.0,
                    "source": self.name,
                })
            return results or None
        except Exception as e:
            logger.warning("Sina market indices failed: %s", e)
            return None

    def _fetch_market_statistics(self) -> Optional[dict]:
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        base_params = {
            "num": "100",
            "sort": "symbol",
            "asc": "1",
            "node": "hs_a",
            "symbol": "",
            "_s_r_a": "page",
        }
        rows: list[dict] = []
        for page in range(1, 80):
            params = {**base_params, "page": str(page)}
            r = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=20)
            r.raise_for_status()
            page_rows = json.loads(r.text)
            if not isinstance(page_rows, list) or not page_rows:
                break
            rows.extend(page_rows)
            if len(page_rows) < int(base_params["num"]):
                break

        if not rows:
            return None

        up_count = down_count = flat_count = limit_up_count = limit_down_count = 0
        total_amount = 0.0
        for item in rows:
            try:
                change_pct = float(item.get("changepercent") or 0)
                amount = float(item.get("amount") or 0)
            except (TypeError, ValueError):
                continue
            total_amount += amount
            if change_pct > 0:
                up_count += 1
            elif change_pct < 0:
                down_count += 1
            else:
                flat_count += 1

            code = str(item.get("symbol") or "")[-6:]
            name = str(item.get("name") or "")
            limit_ratio = 0.10
            if code.startswith(("688", "30")):
                limit_ratio = 0.20
            elif code.startswith(("8", "9", "43")):
                limit_ratio = 0.30
            elif "ST" in name or "*ST" in name:
                limit_ratio = 0.05
            if change_pct >= limit_ratio * 100 - 0.5:
                limit_up_count += 1
            elif change_pct <= -limit_ratio * 100 + 0.5:
                limit_down_count += 1

        return {
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "total_amount": round(total_amount / 1e8, 2),
            "stock_count": up_count + down_count + flat_count,
            "source": self.name,
        }

    async def get_market_statistics(self) -> Optional[dict]:
        try:
            return await asyncio.to_thread(self._fetch_market_statistics)
        except Exception as e:
            logger.warning("Sina market statistics failed: %s", e)
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
