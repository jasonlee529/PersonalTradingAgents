"""CninfoSource — 巨潮资讯网 official disclosure platform.

Wraps the Cninfo (www.cninfo.com.cn) hisAnnouncement/query API
to fetch stock announcements, reports, and regulatory filings.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from src.data.sources.base import DataSource
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_ANNOUNCE_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"


class CninfoSource(DataSource):
    """巨潮资讯网 — CSRC-mandated disclosure platform for A-share announcements."""

    name = "cninfo"

    async def get_quote(self, symbol: str) -> Optional[dict]:
        return None

    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 60) -> Optional[list[dict]]:
        return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return None

    async def get_announcements(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        category: str = "",
        limit: int = 30,
    ) -> Optional[list[dict]]:
        """Fetch announcements for a given stock.

        Args:
            symbol: Stock code e.g. "000001"
            start_date: Start date "YYYY-MM-DD" (defaults to 30 days ago)
            end_date: End date "YYYY-MM-DD" (defaults to today)
            category: Announcement category e.g. "category_ndbg_szsh" (年报)
            limit: Max announcements to return

        Returns:
            List of announcement dicts with title, time, url, etc.
        """
        code = str(normalize_ticker(symbol)).zfill(6)

        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_dt = datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=30)
            start_date = start_dt.strftime("%Y-%m-%d")

        # Determine exchange column
        column = "sse" if code.startswith("6") else "szse"

        payload = {
            "pageNum": "1",
            "pageSize": str(limit),
            "column": column,
            "tabName": "fulltext",
            "stock": code,
            "seDate": f"{start_date}~{end_date}",
        }
        if category:
            payload["category"] = category

        try:
            r = await asyncio.to_thread(
                requests.post,
                _ANNOUNCE_URL,
                data=payload,
                headers={"User-Agent": _UA, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
                timeout=15,
            )
            d = r.json()
            announcements = d.get("announcements", [])
            if not announcements:
                return []

            results = []
            for item in announcements:
                adj_url = item.get("adjunctUrl", "")
                pdf_url = f"http://static.cninfo.com.cn/{adj_url}" if adj_url else ""
                results.append({
                    "title": item.get("announcementTitle", "").strip(),
                    "time": item.get("announcementTime", ""),
                    "announcement_id": item.get("announcementId", ""),
                    "column_id": item.get("columnId", ""),
                    "pdf_url": pdf_url,
                    "source": self.name,
                })
            return results
        except Exception as e:
            logger.warning("Cninfo announcements failed for %s: %s", code, e)
            return None

    async def get_global_news(self, look_back_days: int = 7, limit: int = 10) -> Optional[list[dict]]:
        return None

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    requests.post,
                    _ANNOUNCE_URL,
                    data={"pageNum": "1", "pageSize": "1", "column": "sse", "tabName": "fulltext", "stock": "600519", "seDate": "2024-01-01~2024-01-31"},
                    headers={"User-Agent": _UA},
                    timeout=15,
                ),
                timeout=20,
            )
            return True
        except Exception:
            return False
