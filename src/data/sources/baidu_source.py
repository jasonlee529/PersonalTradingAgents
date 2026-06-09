import asyncio
import logging
from typing import Optional

import requests

from src.data.sources.base import DataSource
from src.utils.logger import rate_limited_warning
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)
_HEADERS = {
    "Host": "finance.pae.baidu.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0",
    "Accept": "application/vnd.finance-web.v1+json",
    "Origin": "https://gushitong.baidu.com",
    "Referer": "https://gushitong.baidu.com/",
}


class BaiduSource(DataSource):
    """Baidu stock concept/sector blocks."""

    name = "baidu"

    async def get_quote(self, symbol: str) -> Optional[dict]: return None
    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 60) -> Optional[list[dict]]: return None
    async def get_fundamentals(self, symbol: str) -> Optional[dict]: return None

    async def fetch_theme_exposure(self, symbol: str) -> Optional[list[dict]]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            url = f'https://finance.pae.baidu.com/api/getrelatedblock?stock=[{{"code":"{code}","market":"ab","type":"stock"}}]&finClientType=pc'
            r = await asyncio.to_thread(requests.get, url, headers=_HEADERS, timeout=10)
            d = r.json()
            if str(d.get("ResultCode", -1)) != "0":
                rate_limited_warning(
                    logger,
                    "baidu.pae_error",
                    "Baidu PAE error: %s",
                    d.get("ResultMsg", ""),
                )
                return None
            categories = d.get("Result", {}).get(code, [])
            result = []
            for cat in categories:
                items = []
                for item in cat.get("list", []):
                    items.append({"name": item.get("name"), "ratio": item.get("ratio"), "desc": item.get("describe", "")})
                result.append({"category": cat.get("name"), "items": items})
            return result
        except Exception as e:
            rate_limited_warning(
                logger,
                "baidu.concept_blocks",
                "Baidu concept blocks failed for %s: %s",
                code,
                e,
            )
            return None

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(requests.get, "https://finance.pae.baidu.com/api/getrelatedblock?stock=[{\"code\":\"000001\",\"market\":\"ab\",\"type\":\"stock\"}]&finClientType=pc", headers=_HEADERS, timeout=10),
                timeout=15,
            )
            return True
        except Exception:
            return False

