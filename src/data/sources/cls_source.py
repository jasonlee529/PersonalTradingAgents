import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import requests

from src.data.sources.base import DataSource

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class CLSSource(DataSource):
    """Cailianshe (财联社) global financial news wire."""

    name = "cls"

    async def get_quote(self, symbol: str) -> Optional[dict]: return None
    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 60) -> Optional[list[dict]]: return None
    async def get_fundamentals(self, symbol: str) -> Optional[dict]: return None

    async def get_global_news(self, look_back_days: int = 7, limit: int = 10) -> Optional[list[dict]]:
        try:
            url = "https://www.cls.cn/nodeapi/telegraphList"
            params = {"rn": str(limit), "page": "1"}
            headers = {"User-Agent": _UA, "Referer": "https://www.cls.cn/"}
            r = await asyncio.to_thread(requests.get, url, params=params, headers=headers, timeout=10)
            if r.status_code != 200:
                logger.debug("CLS global news returned HTTP %s", r.status_code)
                return None
            text = (r.text or "").strip()
            if not text:
                logger.debug("CLS global news returned empty body")
                return None
            try:
                d = r.json()
            except (json.JSONDecodeError, ValueError):
                logger.debug("CLS global news returned non-JSON body: %s", text[:120])
                return None
            articles = []
            for item in d.get("data", {}).get("roll_data", []):
                title = item.get("title", "") or item.get("brief", "")
                content = item.get("content", "") or item.get("brief", "")
                ctime = item.get("ctime", "")
                pub_time = ""
                if ctime:
                    try:
                        pub_time = datetime.fromtimestamp(int(ctime)).strftime("%Y-%m-%d %H:%M")
                    except (ValueError, TypeError, OSError):
                        pub_time = str(ctime)
                articles.append({"title": title, "content": content, "time": pub_time, "source": "CLS Wire"})
            return articles
        except Exception as e:
            logger.debug("CLS global news failed: %s", e)
            return None

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(requests.get, "https://www.cls.cn/nodeapi/telegraphList", params={"rn": "1", "page": "1"}, headers={"User-Agent": _UA}, timeout=10),
                timeout=15,
            )
            return True
        except Exception:
            return False
