import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

import requests

from src.data.sources.base import DataSource
from src.utils.logger import rate_limited_warning
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


class EastmoneySource(DataSource):
    """Eastmoney datacenter, push2, and news APIs."""

    name = "eastmoney"

    def _datacenter(
        self, report_name: str, columns: str = "ALL", filter_str: str = "",
        page_size: int = 50, sort_columns: str = "", sort_types: str = "-1"
    ) -> list[dict]:
        params = {
            "reportName": report_name, "columns": columns, "filter": filter_str,
            "pageNumber": "1", "pageSize": str(page_size),
            "sortColumns": sort_columns, "sortTypes": sort_types,
            "source": "WEB", "client": "WEB",
        }
        r = requests.get(_DATACENTER_URL, params=params, headers={"User-Agent": _UA}, timeout=15)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
        return []

    async def get_quote(self, symbol: str) -> Optional[dict]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            market_code = 1 if code.startswith("6") else 0
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "fltt": "2", "invt": "2",
                "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f170",
                "secid": f"{market_code}.{code}",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=10
            )
            d = r.json().get("data", {})
            if not d:
                return None
            return {
                "symbol": code,
                "name": d.get("f58", ""),
                "price": float(d["f43"]) if d.get("f43") else 0.0,
                "high": float(d["f44"]) if d.get("f44") else 0.0,
                "low": float(d["f45"]) if d.get("f45") else 0.0,
                "open": float(d["f46"]) if d.get("f46") else 0.0,
                "prev_close": float(d["f60"]) if d.get("f60") else 0.0,
                "volume": int(d["f47"]) if d.get("f47") else 0,
                "turnover": float(d["f48"]) if d.get("f48") else 0.0,
                "change_pct": float(d["f170"]) if d.get("f170") else 0.0,
                "source": self.name,
            }
        except Exception as e:
            logger.warning("Eastmoney quote failed for %s: %s", code, e)
            return None

    async def get_balance_sheet(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            data = await asyncio.to_thread(
                self._datacenter, "RPT_DMSK_BS",
                filter_str=f'(SECURITY_CODE="{code}")',
                page_size=20, sort_columns="REPORT_DATE", sort_types="-1"
            )
            return [{"source": self.name, **item} for item in data] if data else None
        except Exception as e:
            logger.warning("Eastmoney balance sheet failed for %s: %s", code, e)
            return None

    async def get_cashflow(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            data = await asyncio.to_thread(
                self._datacenter, "RPT_DMSK_CF",
                filter_str=f'(SECURITY_CODE="{code}")',
                page_size=20, sort_columns="REPORT_DATE", sort_types="-1"
            )
            return [{"source": self.name, **item} for item in data] if data else None
        except Exception as e:
            logger.warning("Eastmoney cashflow failed for %s: %s", code, e)
            return None

    async def get_income_statement(self, symbol: str, freq: str = "quarterly") -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            data = await asyncio.to_thread(
                self._datacenter, "RPT_DMSK_IS",
                filter_str=f'(SECURITY_CODE="{code}")',
                page_size=20, sort_columns="REPORT_DATE", sort_types="-1"
            )
            return [{"source": self.name, **item} for item in data] if data else None
        except Exception as e:
            logger.warning("Eastmoney income statement failed for %s: %s", code, e)
            return None

    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 60) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        # Shanghai index codes start with 000/001 but belong to market 1
        _sh_index_codes = {"000001", "000016", "000300", "000905"}
        market_code = 1 if code.startswith("6") or code in _sh_index_codes else 0
        secid = f"{market_code}.{code}"
        klt = "101" if period == "1d" else "102" if period == "1w" else "101"
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=limit * 2)).strftime("%Y%m%d")

        url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            "secid": secid,
            "klt": klt,
            "fqt": "0",
            "beg": start,
            "end": end,
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }
        try:
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15
            )
            d = r.json()
            klines = d.get("data", {}).get("klines", [])
            if not klines:
                return None
            records = []
            for line in klines[-limit:]:
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
                    "amplitude": float(parts[7]) if len(parts) > 7 and parts[7] else 0.0,
                    "change_pct": float(parts[8]) if len(parts) > 8 and parts[8] else 0.0,
                    "change_amt": float(parts[9]) if len(parts) > 9 and parts[9] else 0.0,
                    "turnover_rate": float(parts[10]) if len(parts) > 10 and parts[10] else 0.0,
                })
            return records
        except Exception as e:
            logger.warning("Eastmoney kline failed for %s: %s", code, e)
            return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            market_code = 1 if code.startswith("6") else 0
            url = "https://push2.eastmoney.com/api/qt/stock/get"
            params = {
                "fltt": "2", "invt": "2",
                "fields": "f57,f58,f84,f85,f116,f117,f127,f162,f167,f168,f169,f183,f184,f185,f186,f187,f189,f190",
                "secid": f"{market_code}.{code}",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=10
            )
            d = r.json().get("data", {})
            result = {"symbol": code, "source": self.name}
            field_map = {
                "f58": "name",
                "f127": "industry",
                "f84": "total_shares",
                "f85": "float_shares",
                "f116": "total_mcap",
                "f117": "float_mcap",
                "f189": "list_date",
                "f162": "pe_ttm",
                "f167": "pb",
                "f168": "market_cap",
                "f169": "float_market_cap",
                "f183": "net_profit",
                "f184": "net_profit_growth",
                "f185": "main_revenue",
                "f186": "main_revenue_growth",
                "f187": "roe_weighted",
                "f190": "gross_margin",
            }
            for source_field, target_field in field_map.items():
                if d.get(source_field):
                    result[target_field] = d[source_field]
            return result
        except Exception as e:
            logger.warning("Eastmoney fundamentals failed for %s: %s", code, e)
            return None

    @staticmethod
    def _number_or_none(value):
        if value in (None, "", "-"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int_or_none(value):
        number = EastmoneySource._number_or_none(value)
        return int(number) if number is not None else None

    @staticmethod
    def _limit_up_time(value) -> str | None:
        if value in (None, "", "-"):
            return None
        text = str(value).strip()
        if len(text) == 6 and text.isdigit():
            return f"{text[:2]}:{text[2:4]}:{text[4:6]}"
        return text

    async def get_limit_up_stocks(
        self, trade_date: str = "", market: str = "all"
    ) -> Optional[list[dict]]:
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        # 尝试所有数据源，合并结果去重
        all_items: dict[str, dict] = {}
        sources = [
            ("push2ex", self._fetch_limit_up_push2ex(trade_date)),
            ("quote.ztb", self._fetch_limit_up_quote_ztb(trade_date)),
            ("datacenter", self._fetch_limit_up_datacenter(trade_date)),
        ]

        for source_name, future in sources:
            try:
                items = await future
                if items:
                    logger.info("eastmoney %s returned %d limit-up stocks for %s", source_name, len(items), trade_date)
                    for item in items:
                        code = item.get("symbol", "")
                        if code and code not in all_items:
                            all_items[code] = item
            except Exception as e:
                logger.warning("eastmoney %s failed for %s: %s", source_name, trade_date, e)

        if all_items:
            return list(all_items.values())

        # 所有数据源都失败
        logger.warning("all eastmoney sources failed for %s", trade_date)
        return None

    async def _fetch_limit_up_push2ex(self, trade_date: str) -> Optional[list[dict]]:
        """原 push2ex 涨停池专用接口。"""
        date_param = trade_date.replace("-", "")
        try:
            url = "https://push2ex.eastmoney.com/getTopicZTPool"
            params = {
                "ut": "7eea3edcaed734bea9cbfc24409ed989",
                "d": date_param,
                "pageindex": "0",
                "pagesize": "10000",
                "sort": "fbt:asc",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=15
            )
            data = r.json().get("data") or {}
            rows = data.get("pool") or []
            items = []
            for row in rows:
                code = str(row.get("c") or row.get("code") or "").zfill(6)
                if not code or code == "000000":
                    continue
                items.append({
                    "symbol": code,
                    "name": row.get("n") or row.get("name") or "",
                    "market": "sh" if code.startswith("6") else "sz",
                    "trade_date": trade_date,
                    "price": self._number_or_none(row.get("p")),
                    "change_pct": self._number_or_none(row.get("zdp")),
                    "volume": self._int_or_none(row.get("volume") or row.get("v")),
                    "turnover": self._number_or_none(row.get("amount")),
                    "turnover_rate": self._number_or_none(row.get("turnoverrate")),
                    "first_limit_up_time": self._limit_up_time(row.get("fbt")),
                    "last_limit_up_time": self._limit_up_time(row.get("lbt")),
                    "seal_amount": self._number_or_none(row.get("fund")),
                    "consecutive_days": self._int_or_none(row.get("lbc")),
                    "reason": row.get("hybk") or row.get("reason") or "",
                    "source": self.name,
                })
            return items if items else None
        except Exception as e:
            logger.warning("Eastmoney push2ex limit-up failed for %s: %s", trade_date, e)
            return None

    async def _fetch_limit_up_quote_ztb(self, trade_date: str) -> Optional[list[dict]]:
        """通过 quote.eastmoney.com/ztb/detail 获取涨停股票数据。"""
        date_param = trade_date.replace("-", "")
        try:
            # quote.eastmoney.com/ztb/detail 页面的数据接口
            url = "https://quote.eastmoney.com/ztb/detail"
            params = {
                "date": date_param,
                "page": "1",
                "pageSize": "10000",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"}, timeout=15
            )
            # 解析返回的 JSON 数据
            data = r.json()
            rows = data.get("data") or data.get("list") or []
            if not rows:
                return None

            items = []
            for row in rows:
                code = str(row.get("code") or row.get("ztdm") or "").zfill(6)
                if not code or code == "000000":
                    continue
                items.append({
                    "symbol": code,
                    "name": row.get("name") or row.get("ztmc") or "",
                    "market": "sh" if code.startswith("6") else "sz",
                    "trade_date": trade_date,
                    "price": self._number_or_none(row.get("price") or row.get("ztdj")),
                    "change_pct": self._number_or_none(row.get("zdf") or row.get("zdp")),
                    "volume": self._int_or_none(row.get("volume") or row.get("cjl")),
                    "turnover": self._number_or_none(row.get("turnover") or row.get("cjje")),
                    "turnover_rate": self._number_or_none(row.get("换手率") or row.get("hsl")),
                    "first_limit_up_time": row.get("firstTime") or row.get("first_limit_up_time"),
                    "last_limit_up_time": row.get("lastTime") or row.get("last_limit_up_time"),
                    "seal_amount": self._number_or_none(row.get("sealAmount") or row.get("fund")),
                    "consecutive_days": self._int_or_none(row.get("days") or row.get("lbc")),
                    "reason": row.get("reason") or row.get("hybk") or "",
                    "source": self.name,
                })
            return items if items else None
        except Exception as e:
            logger.warning("Eastmoney quote.ztb limit-up failed for %s: %s", trade_date, e)
            return None

    async def _fetch_limit_up_datacenter(self, trade_date: str) -> Optional[list[dict]]:
        """通过龙虎榜 datacenter 接口获取涨停股票（备选方案）。"""
        try:
            url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
            params = {
                "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
                "columns": "SECURITY_CODE,SECURITY_NAME_ABBR,CHANGE_RATE,CLOSE_PRICE,ACCUM_AMOUNT,ACCUM_VOLUME,TURNOVERRATE,TRADE_DATE",
                "pageSize": "500",
                "pageNumber": "1",
                "sortColumns": "CHANGE_RATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
                "filter": f"(TRADE_DATE>='{trade_date}')",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA, "Referer": "https://data.eastmoney.com/"}, timeout=15
            )
            result = r.json().get("result") or {}
            rows = result.get("data") or []
            if not rows:
                return None

            # 按涨幅筛选涨停股：主板 >=9.9%，创业板/科创板 >=19.9%
            seen: set[str] = set()
            items: list[dict] = []
            for row in rows:
                code = str(row.get("SECURITY_CODE") or "").zfill(6)
                if not code or code in seen:
                    continue
                change = self._number_or_none(row.get("CHANGE_RATE"))
                if change is None:
                    continue
                # 主板涨停阈值 10%，创业板/科创板 20%
                is_mainboard = code.startswith(("60", "00"))
                threshold = 9.9 if is_mainboard else 19.9
                if change < threshold:
                    continue
                seen.add(code)
                items.append({
                    "symbol": code,
                    "name": row.get("SECURITY_NAME_ABBR") or "",
                    "market": "sh" if code.startswith("6") else "sz",
                    "trade_date": trade_date,
                    "price": self._number_or_none(row.get("CLOSE_PRICE")),
                    "change_pct": change,
                    "volume": self._int_or_none(row.get("ACCUM_VOLUME")),
                    "turnover": self._number_or_none(row.get("ACCUM_AMOUNT")),
                    "turnover_rate": self._number_or_none(row.get("TURNOVERRATE")),
                    "first_limit_up_time": None,
                    "last_limit_up_time": None,
                    "seal_amount": None,
                    "consecutive_days": None,
                    "reason": "",
                    "source": self.name,
                })
            return items if items else None
        except Exception as e:
            logger.warning("Eastmoney datacenter limit-up fallback failed for %s: %s", trade_date, e)
            return None

    async def get_news(self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 20) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            url = "https://search-api-web.eastmoney.com/search/jsonp"
            inner = {
                "uid": "", "keyword": code, "type": ["cmsArticleWebOld"],
                "client": "web", "clientType": "web", "clientVersion": "curr",
                "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": limit, "preTag": "", "postTag": ""}}
            }
            params = {"cb": "callback", "param": json.dumps(inner, ensure_ascii=False), "_": "1"}
            headers = {"Referer": "https://so.eastmoney.com/", "User-Agent": _UA}
            r = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=15)
            text = r.text
            text = text[text.index("(") + 1:text.rindex(")")]
            data = json.loads(text)
            articles = []
            for item in data.get("result", {}).get("cmsArticleWebOld", []):
                articles.append({
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "time": item.get("date", ""),
                    "source": item.get("mediaName", "东方财富"),
                    "url": item.get("url", ""),
                })
            return articles
        except Exception as e:
            logger.warning("Eastmoney news failed for %s: %s", code, e)
            return None

    async def get_global_news(self, look_back_days: int = 7, limit: int = 10) -> Optional[list[dict]]:
        try:
            url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
            params = {"client": "web", "biz": "web_724", "fastColumn": "102", "sortEnd": "", "pageSize": str(limit), "req_trace": str(uuid.uuid4())}
            headers = {"User-Agent": _UA, "Referer": "https://kuaixun.eastmoney.com/"}
            r = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=10)
            d = r.json()
            articles = []
            for item in d.get("data", {}).get("fastNewsList", []):
                articles.append({
                    "title": item.get("title", ""),
                    "content": item.get("summary", "")[:200],
                    "time": item.get("showTime", ""),
                    "source": "Eastmoney Global",
                })
            return articles
        except Exception as e:
            logger.warning("Eastmoney global news failed: %s", e)
            return None

    async def fetch_order_flow_profile(self, symbol: str, include_history: bool = True) -> Optional[dict]:
        code = str(normalize_ticker(symbol)).zfill(6)
        secid = f"1.{code}" if code.startswith("6") else f"0.{code}"
        try:
            url_rt = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
            params_rt = {"secid": secid, "klt": 1, "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57"}
            r = await asyncio.to_thread(requests.get, url_rt, params=params_rt, timeout=10)
            klines = r.json().get("data", {}).get("klines", [])
            result = {"symbol": code, "realtime": [], "source": self.name}
            if klines:
                for line in klines[-10:]:
                    parts = line.split(",")
                    if len(parts) >= 6:
                        result["realtime"].append({
                            "time": parts[0],
                            "main_net": float(parts[1]),
                            "small": float(parts[2]),
                            "mid": float(parts[3]),
                            "large": float(parts[4]),
                            "super": float(parts[5]),
                        })
            if include_history:
                url_hist = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
                params_hist = {"secid": secid, "lmt": 20, "klt": 101, "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57"}
                rh = await asyncio.to_thread(requests.get, url_hist, params=params_hist, timeout=10)
                dh = rh.json()
                hist = dh.get("data", {}).get("klines", [])
                result["history"] = []
                for line in hist:
                    parts = line.split(",")
                    if len(parts) >= 6:
                        result["history"].append({
                            "date": parts[0], "main_net": float(parts[1]),
                            "small": float(parts[2]), "mid": float(parts[3]),
                            "large": float(parts[4]), "super": float(parts[5]),
                        })
            return result
        except Exception as e:
            rate_limited_warning(
                logger,
                "eastmoney.fund_flow",
                "Eastmoney fund flow failed for %s: %s",
                code,
                e,
            )
            return None

    async def fetch_trading_seat_activity(self, symbol: str, trade_date: str = "", look_back_days: int = 30) -> Optional[dict]:
        code = str(normalize_ticker(symbol)).zfill(6)
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        end_dt = datetime.strptime(trade_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=look_back_days)
        start_str = start_dt.strftime("%Y-%m-%d")
        try:
            appearances = await asyncio.to_thread(
                self._datacenter, "RPT_DAILYBILLBOARD_DETAILSNEW",
                filter_str=f"(TRADE_DATE>='{start_str}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
                page_size=50, sort_columns="TRADE_DATE", sort_types="-1"
            )
            latest_date = str(appearances[0].get("TRADE_DATE", ""))[:10] if appearances else ""
            buy_seats, sell_seats = [], []
            if latest_date:
                buy_seats = await asyncio.to_thread(
                    self._datacenter, "RPT_BILLBOARD_DAILYDETAILSBUY",
                    filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                    page_size=10, sort_columns="BUY", sort_types="-1"
                )
                sell_seats = await asyncio.to_thread(
                    self._datacenter, "RPT_BILLBOARD_DAILYDETAILSSELL",
                    filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                    page_size=10, sort_columns="SELL", sort_types="-1"
                )
            return {
                "symbol": code, "appearances": appearances,
                "buy_seats": buy_seats, "sell_seats": sell_seats,
                "source": self.name,
            }
        except Exception as e:
            logger.warning("Eastmoney dragon-tiger failed for %s: %s", code, e)
            return None

    async def fetch_supply_unlock_schedule(self, symbol: str, trade_date: str = "", forward_days: int = 90) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        if not trade_date:
            trade_date = datetime.now().strftime("%Y-%m-%d")
        try:
            history = await asyncio.to_thread(
                self._datacenter, "RPT_LIFT_STAGE",
                filter_str=f"(SECURITY_CODE=\"{code}\")",
                page_size=15, sort_columns="FREE_DATE", sort_types="-1"
            )
            end_dt = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)
            upcoming = await asyncio.to_thread(
                self._datacenter, "RPT_LIFT_STAGE",
                filter_str=f"(SECURITY_CODE=\"{code}\")(FREE_DATE>='{trade_date}')(FREE_DATE<='{end_dt.strftime('%Y-%m-%d')}')",
                page_size=20, sort_columns="FREE_DATE", sort_types="1"
            )
            return {"symbol": code, "history": history, "upcoming": upcoming, "source": self.name}
        except Exception as e:
            logger.warning("Eastmoney lockup expiry failed for %s: %s", code, e)
            return None

    async def fetch_peer_industry_snapshot(self, symbol: str, top_n: int = 20) -> Optional[list[dict]]:
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {"pn": "1", "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2", "fs": "m:90+t:2", "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207"}
            r = await asyncio.to_thread(requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=15)
            d = r.json()
            items = d.get("data", {}).get("diff", [])
            return [{"name": i.get("f14"), "change_pct": i.get("f3"), "up_count": i.get("f104"), "down_count": i.get("f105"), "leader": i.get("f140")} for i in items]
        except Exception as e:
            logger.warning("Eastmoney industry comparison failed: %s", e)
            return None

    async def list_concept_boards(self, limit: int = 100) -> Optional[list[dict]]:
        """Return concept board list: code, name, change_pct.

        Uses fs=m:90+t:3 on push2 clist endpoint.
        """
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": str(limit), "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fs": "m:90+t:3",
                "fields": "f2,f3,f4,f12,f13,f14",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=15
            )
            d = r.json()
            items = d.get("data", {}).get("diff", [])
            return [
                {
                    "code": i.get("f12"),
                    "name": i.get("f14"),
                    "change_pct": i.get("f3"),
                    "source": self.name,
                }
                for i in items if i.get("f12")
            ]
        except Exception as e:
            rate_limited_warning(
                logger,
                "eastmoney.concept_boards",
                "Eastmoney concept boards failed: %s",
                e,
            )
            return None

    async def list_industry_boards(self, limit: int = 100) -> Optional[list[dict]]:
        """Return industry board list: code, name, change_pct.

        Uses fs=m:90+t:2 on push2 clist endpoint.
        """
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": str(limit), "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f13,f14",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=15
            )
            d = r.json()
            items = d.get("data", {}).get("diff", [])
            return [
                {
                    "code": i.get("f12"),
                    "name": i.get("f14"),
                    "change_pct": i.get("f3"),
                    "source": self.name,
                }
                for i in items if i.get("f12")
            ]
        except Exception as e:
            rate_limited_warning(
                logger,
                "eastmoney.industry_boards",
                "Eastmoney industry boards failed: %s",
                e,
            )
            return None

    async def get_board_stocks(self, board_code: str, limit: int = 100) -> Optional[list[dict]]:
        """Return constituent stocks for a specific board.

        Uses fs=b:BKxxxx on push2 clist endpoint.
        """
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1", "pz": str(limit), "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fs": f"b:{board_code}",
                "fields": "f2,f3,f4,f12,f13,f14",
            }
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=15
            )
            d = r.json()
            items = d.get("data", {}).get("diff", [])
            return [
                {
                    "symbol": i.get("f12"),
                    "name": i.get("f14"),
                    "price": i.get("f2"),
                    "change_pct": i.get("f3"),
                    "source": self.name,
                }
                for i in items if i.get("f12")
            ]
        except Exception as e:
            rate_limited_warning(
                logger,
                "eastmoney.board_stocks",
                "Eastmoney board stocks failed for %s: %s",
                board_code,
                e,
            )
            return None

    async def get_research_reports(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        limit: int = 30,
    ) -> Optional[list[dict]]:
        """Fetch stock research reports from Eastmoney report API.

        Args:
            symbol: Stock code e.g. "000001"
            start_date: Start date "YYYY-MM-DD" (defaults to 1 year ago)
            end_date: End date "YYYY-MM-DD" (defaults to today)
            limit: Max reports to return

        Returns:
            List of research report dicts with title, org, rating, predictions, PDF URL.
        """
        code = str(normalize_ticker(symbol)).zfill(6)

        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=365)
            start_date = start_dt.strftime("%Y-%m-%d")

        url = "https://reportapi.eastmoney.com/report/list"
        params = {
            "industryCode": "*",
            "pageSize": str(min(limit, 500)),
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": start_date,
            "endTime": end_date,
            "pageNo": "1",
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": code,
            "rcode": "",
            "p": "1",
            "pageNum": "1",
            "pageNumber": "1",
        }

        try:
            r = await asyncio.to_thread(
                requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=15
            )
            d = r.json()
            data = d.get("data", [])
            if not data:
                return []

            results = []
            for item in data[:limit]:
                info_code = item.get("infoCode", "")
                pdf_url = f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf" if info_code else ""
                results.append({
                    "title": item.get("title", ""),
                    "stock_name": item.get("stockName", ""),
                    "stock_code": item.get("stockCode", ""),
                    "org_name": item.get("orgSName", ""),
                    "publish_date": item.get("publishDate", ""),
                    "rating": item.get("emRatingName", ""),
                    "industry": item.get("indvInduName", ""),
                    "predict_this_year_eps": item.get("predictThisYearEps"),
                    "predict_this_year_pe": item.get("predictThisYearPe"),
                    "predict_next_year_eps": item.get("predictNextYearEps"),
                    "predict_next_year_pe": item.get("predictNextYearPe"),
                    "pdf_url": pdf_url,
                    "source": self.name,
                })
            return results
        except Exception as e:
            logger.warning("Eastmoney research reports failed for %s: %s", code, e)
            return None

    # ---- Market overview ----

    async def get_market_indices(self) -> Optional[list[dict]]:
        """Fetch major index quotes via push2."""
        indices_map = {
            "1.000001": "上证指数",
            "0.399001": "深证成指",
            "0.399006": "创业板指",
            "1.000688": "科创50",
            "1.000016": "上证50",
            "0.399300": "沪深300",
        }
        url = "https://push2.eastmoney.com/api/qt/stock/get"
        results = []
        for secid, name in indices_map.items():
            try:
                params = {
                    "fltt": "2", "invt": "2",
                    "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f170",
                    "secid": secid,
                }
                r = await asyncio.to_thread(
                    requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=10
                )
                d = r.json().get("data", {})
                if not d:
                    continue
                current = float(d["f43"]) if d.get("f43") else 0.0
                change = float(d["f170"]) if d.get("f170") else 0.0
                prev = current - change if current or change else 0.0
                change_pct = (change / prev * 100) if prev else 0.0
                results.append({
                    "code": secid.split(".")[1],
                    "name": name,
                    "current": current,
                    "change": change,
                    "change_pct": round(change_pct, 2),
                    "open": float(d["f46"]) if d.get("f46") else 0.0,
                    "high": float(d["f44"]) if d.get("f44") else 0.0,
                    "low": float(d["f45"]) if d.get("f45") else 0.0,
                    "volume": int(d["f47"]) if d.get("f47") else 0,
                    "amount": float(d["f48"]) if d.get("f48") else 0.0,
                    "amplitude": 0.0,
                })
            except Exception as e:
                logger.debug("Eastmoney index %s failed: %s", secid, e)
        return results if results else None

    async def get_market_statistics(self) -> Optional[dict]:
        """Fetch all A-share ticks and compute breadth stats."""
        try:
            all_stocks = await self.get_all_stock_quotes()
            if not all_stocks:
                return None

            up_count = down_count = flat_count = limit_up_count = limit_down_count = 0
            total_amount = 0.0

            for stock in all_stocks:
                change_pct = float(stock.get("change_pct") or 0)
                amount = float(stock.get("turnover") or 0)
                total_amount += amount

                if change_pct > 0:
                    up_count += 1
                elif change_pct < 0:
                    down_count += 1
                else:
                    flat_count += 1

                if stock.get("is_limit_up"):
                    limit_up_count += 1
                if stock.get("is_limit_down"):
                    limit_down_count += 1

            return {
                "total_stocks": len(all_stocks),
                "up_count": up_count,
                "down_count": down_count,
                "flat_count": flat_count,
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
                "total_turnover": total_amount,
            }
        except Exception as e:
            logger.warning("Eastmoney market statistics failed: %s", e)
            return None

    async def get_all_stock_quotes(self) -> Optional[list[dict]]:
        """获取全市场所有 A 股的实时行情数据（含涨停/跌停状态）。"""
        try:
            url = "https://push2.eastmoney.com/api/qt/clist/get"

            sectors = [
                ("m:0+t:6", "深市主板"),
                ("m:0+t:80", "创业板"),
                ("m:0+t:13", "深市主板"),
                ("m:1+t:2", "沪市主板"),
                ("m:1+t:23", "沪市主板"),
                ("m:1+t:10", "科创板"),
                ("m:1+t:4", "沪市主板"),
            ]

            all_stocks: list[dict] = []
            seen_symbols: set[str] = set()

            for secid_filters, _label in sectors:
                page = 1
                page_size = 5000
                while True:
                    params = {
                        "pn": str(page),
                        "pz": str(page_size),
                        "po": "1",
                        "np": "1",
                        "fltt": "2",
                        "invt": "2",
                        "fs": secid_filters,
                        "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13,f14,f15,f16,f17,f18,f20,f21,f22,f23,f24,f25,f112,f113,f114,f128,f140,f141,f162,f167,f168,f169,f170,f171,f183,f184,f185,f186,f187,f189,f190",
                    }
                    r = await asyncio.to_thread(
                        requests.get, url, params=params, headers={"User-Agent": _UA}, timeout=20
                    )
                    data = r.json()
                    items = data.get("data", {}).get("diff", []) or []
                    if not items:
                        break

                    for item in items:
                        symbol = str(item.get("f12") or "").strip().zfill(6)
                        if not symbol or symbol in seen_symbols:
                            continue
                        seen_symbols.add(symbol)

                        market_code = str(item.get("f13") or (1 if symbol.startswith("6") else 0))
                        market = "sh" if market_code == "1" else "sz"

                        price_raw = item.get("f2")
                        change_pct_raw = item.get("f3")
                        change_amount_raw = item.get("f4")
                        volume_raw = item.get("f5")
                        turnover_raw = item.get("f6")
                        high_raw = item.get("f15")
                        low_raw = item.get("f16")
                        open_raw = item.get("f17")
                        prev_close_raw = item.get("f18")
                        turnover_rate_raw = item.get("f8")
                        pe_ratio_raw = item.get("f9")
                        amplitude_raw = item.get("f7")
                        total_market_cap_raw = item.get("f20")
                        float_market_cap_raw = item.get("f21")
                        limit_up_price_raw = item.get("f22")
                        limit_down_price_raw = item.get("f23")
                        name = str(item.get("f14") or "")

                        price = float(price_raw) if price_raw not in (None, "-", "") else 0.0
                        change_pct = float(change_pct_raw) if change_pct_raw not in (None, "-", "") else 0.0
                        change_amount = float(change_amount_raw) if change_amount_raw not in (None, "-", "") else 0.0
                        volume = int(float(volume_raw or 0)) if volume_raw not in (None, "-", "") else 0
                        turnover = float(turnover_raw) if turnover_raw not in (None, "-", "") else 0.0
                        high = float(high_raw) if high_raw not in (None, "-", "") else 0.0
                        low = float(low_raw) if low_raw not in (None, "-", "") else 0.0
                        open_price = float(open_raw) if open_raw not in (None, "-", "") else 0.0
                        prev_close = float(prev_close_raw) if prev_close_raw not in (None, "-", "") else 0.0
                        turnover_rate = float(turnover_rate_raw) if turnover_rate_raw not in (None, "-", "") else None
                        pe_ratio = float(pe_ratio_raw) if pe_ratio_raw not in (None, "-", "") else None
                        amplitude = float(amplitude_raw) if amplitude_raw not in (None, "-", "") else None
                        total_market_cap = float(total_market_cap_raw) if total_market_cap_raw not in (None, "-", "") else None
                        float_market_cap = float(float_market_cap_raw) if float_market_cap_raw not in (None, "-", "") else None
                        limit_up_price = float(limit_up_price_raw) if limit_up_price_raw not in (None, "-", "") else None
                        limit_down_price = float(limit_down_price_raw) if limit_down_price_raw not in (None, "-", "") else None

                        is_limit_up = False
                        is_limit_down = False
                        if limit_up_price and price >= limit_up_price - 0.001:
                            is_limit_up = True
                        elif limit_down_price and price <= limit_down_price + 0.001:
                            is_limit_down = True

                        all_stocks.append({
                            "symbol": symbol,
                            "name": name,
                            "market": market,
                            "price": price,
                            "change_pct": round(change_pct, 2),
                            "change_amount": round(change_amount, 2),
                            "volume": volume,
                            "turnover": turnover,
                            "high": high,
                            "low": low,
                            "open": open_price,
                            "prev_close": prev_close,
                            "turnover_rate": turnover_rate,
                            "pe_ratio": pe_ratio,
                            "amplitude": amplitude,
                            "total_market_cap": total_market_cap,
                            "float_market_cap": float_market_cap,
                            "limit_up_price": limit_up_price,
                            "limit_down_price": limit_down_price,
                            "is_limit_up": is_limit_up,
                            "is_limit_down": is_limit_down,
                            "board": "sh_main" if symbol.startswith("6") else "sz_main",
                        })

                    if len(items) < page_size:
                        break
                    page += 1
                    if page > 10:
                        break

            logger.info("Eastmoney all-stock quotes: collected %d stocks", len(all_stocks))
            return all_stocks if all_stocks else None
        except Exception as e:
            logger.warning("Eastmoney all-stock quotes failed: %s", e)
            return None

    async def get_sector_rankings(self, n: int = 5) -> Optional[tuple[list[dict], list[dict]]]:
        """Return top and bottom sectors using industry board list."""
        try:
            boards = await self.list_industry_boards(limit=200)
            if not boards:
                return None
            # Sort by change_pct
            boards_sorted = sorted(
                [b for b in boards if b.get("change_pct") is not None],
                key=lambda x: float(x.get("change_pct") or 0),
                reverse=True,
            )
            top = [{"name": b["name"], "change_pct": float(b.get("change_pct") or 0)} for b in boards_sorted[:n]]
            bottom = [{"name": b["name"], "change_pct": float(b.get("change_pct") or 0)} for b in boards_sorted[-n:]]
            return top, bottom
        except Exception as e:
            logger.warning("Eastmoney sector rankings failed: %s", e)
            return None

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._datacenter, "RPT_DAILYBILLBOARD_DETAILSNEW", filter_str="(SECURITY_CODE=\"000001\")", page_size=1),
                timeout=15,
            )
            return True
        except Exception:
            return False

