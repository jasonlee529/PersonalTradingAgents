import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

import requests

from src.config import persist_env_file_values
from src.data.sources.base import DataSource
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_REFERER = "https://xueqiu.com/"
_XUEQIU_HOME = "https://xueqiu.com"
_STATUS_SEARCH_URL = "https://xueqiu.com/query/v1/symbol/search/status.json"


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", str(text or ""))
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&#34;", '"'),
        ("&#39;", "'"),
    ):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


class XueqiuSource(DataSource):
    """Xueqiu stock community posts as a domestic sentiment/news source.

    Xueqiu requires authenticated cookies for these APIs. This source makes a
    single request and returns None on any failure so the collector can fall
    back to lower-priority providers without retrying.
    """

    name = "xueqiu"

    def __init__(self, settings=None):
        self._settings = settings
        self._configured_cookie = str(getattr(settings, "xueqiu_cookie", "") or "").strip()
        self.auto_cookie = bool(getattr(settings, "xueqiu_auto_cookie", True))
        self.timeout = float(getattr(settings, "xueqiu_timeout", 10) or 10)
        self._session = requests.Session()
        self._cookies_initialized = False

    async def get_quote(self, symbol: str) -> Optional[dict]:
        return None

    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return None

    @staticmethod
    def _to_xueqiu_symbol(symbol: str) -> str:
        code = str(normalize_ticker(symbol)).strip().upper()
        if code.startswith(("SH", "SZ", "BJ")):
            return code
        if len(code) == 5 and code.isdigit():
            return code
        code = code.zfill(6) if code.isdigit() else code
        if code.startswith(("6", "9")):
            return f"SH{code}"
        if code.startswith(("8", "4")):
            return f"BJ{code}"
        return f"SZ{code}"

    def _inject_cookie_string(self, cookie_str: str) -> bool:
        loaded = False
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            self._session.cookies.set(
                name.strip(),
                value.strip(),
                domain=".xueqiu.com",
                path="/",
            )
            loaded = True
        if loaded:
            logger.info("Xueqiu cookie loaded from configured XUEQIU_COOKIE")
        return loaded

    def _cookie_string_from_session(self) -> str:
        pairs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for cookie in self._session.cookies:
            name = getattr(cookie, "name", "") or ""
            value = getattr(cookie, "value", "") or ""
            domain = str(getattr(cookie, "domain", "") or "")
            if not name or not value:
                continue
            if domain and "xueqiu.com" not in domain:
                continue
            if name in seen:
                continue
            seen.add(name)
            pairs.append((name, value))
        ordered = sorted(pairs, key=lambda item: (item[0] != "xq_a_token", item[0]))
        return "; ".join(f"{name}={value}" for name, value in ordered)

    def _persist_cookie_string(self) -> None:
        settings = self._settings
        if settings is None:
            return
        cookie_string = self._cookie_string_from_session()
        if "xq_a_token=" not in cookie_string:
            return
        env_path = getattr(settings, "settings_env_path", ".env")
        try:
            persist_env_file_values(env_path, {"XUEQIU_COOKIE": cookie_string})
            logger.info("Xueqiu cookie persisted to %s", env_path)
        except Exception as e:
            logger.debug("Xueqiu cookie persist failed: %s", e)

    def _load_cookies_from_browser(self) -> bool:
        try:
            try:
                import rookiepy

                cookies = rookiepy.chrome([".xueqiu.com"])
                if not any(c.get("name") == "xq_a_token" for c in cookies):
                    logger.info("Xueqiu browser cookie lookup found no xq_a_token")
                    return False
                for cookie in cookies:
                    self._session.cookies.set(
                        cookie.get("name", ""),
                        cookie.get("value", ""),
                        domain=cookie.get("domain") or ".xueqiu.com",
                        path=cookie.get("path") or "/",
                    )
                self._persist_cookie_string()
                logger.info("Xueqiu cookie loaded from browser via rookiepy")
                return True
            except ImportError:
                import browser_cookie3

                cookies = list(browser_cookie3.chrome(domain_name=".xueqiu.com"))
                if not any(c.name == "xq_a_token" for c in cookies):
                    logger.info("Xueqiu browser cookie lookup found no xq_a_token")
                    return False
                for cookie in cookies:
                    self._session.cookies.set_cookie(cookie)
                self._persist_cookie_string()
                logger.info("Xueqiu cookie loaded from browser via browser_cookie3")
                return True
        except Exception as e:
            logger.debug("Xueqiu browser cookie load failed: %s", e)
            return False

    def _load_homepage_cookies(self) -> bool:
        try:
            response = self._session.get(
                _XUEQIU_HOME,
                headers={"User-Agent": _UA, "Referer": _REFERER},
                timeout=self.timeout,
            )
            response.raise_for_status()
            logger.info(
                "Xueqiu homepage visit succeeded with status=%s; cookie_keys=%s",
                response.status_code,
                list(self._session.cookies.keys()),
            )
            return bool(self._session.cookies)
        except Exception as e:
            logger.debug("Xueqiu homepage cookie load failed: %s", e)
            return False

    def _ensure_cookies(self) -> bool:
        if self._cookies_initialized:
            return bool(self._session.cookies)

        loaded = False
        if self._configured_cookie:
            logger.info("Xueqiu trying configured cookie from env")
            loaded = self._inject_cookie_string(self._configured_cookie)
        if not self.auto_cookie:
            self._cookies_initialized = True
            logger.info("Xueqiu auto cookie disabled; loaded=%s", loaded)
            return loaded
        if not loaded:
            logger.info("Xueqiu trying browser cookie lookup")
            loaded = self._load_cookies_from_browser()
        if not loaded:
            logger.info("Xueqiu trying homepage fallback cookie bootstrap")
            loaded = self._load_homepage_cookies()

        self._cookies_initialized = True
        logger.info(
            "Xueqiu cookie bootstrap finished loaded=%s has_xq_a_token=%s",
            loaded,
            "xq_a_token" in self._session.cookies.keys(),
        )
        return loaded

    def _fetch_statuses(self, xq_symbol: str, limit: int) -> dict:
        if not self._ensure_cookies():
            return {}
        headers = {
            "User-Agent": _UA,
            "Referer": _REFERER,
        }
        params = {
            "count": str(min(max(limit, 1), 50)),
            "comment": "0",
            "symbol": xq_symbol,
            "hl": "0",
            "source": "all",
            "sort": "time",
            "page": "1",
            "q": "",
        }
        response = self._session.get(
            _STATUS_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        list_count = len(data.get("list") or data.get("statuses") or [])
        status_code = getattr(response, "status_code", "unknown")
        headers_obj = getattr(response, "headers", {}) or {}
        logger.info(
            "Xueqiu status fetch succeeded symbol=%s status=%s content_type=%s items=%s",
            xq_symbol,
            status_code,
            headers_obj.get("content-type", ""),
            list_count,
        )
        return data

    @staticmethod
    def _created_at(value) -> str:
        if value is None or value == "":
            return ""
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    def _normalise_status(self, item: dict) -> Optional[dict]:
        title = _strip_html(item.get("title") or "")
        content = _strip_html(
            item.get("text")
            or item.get("description")
            or item.get("source")
            or item.get("content")
            or ""
        )
        if not title:
            title = content[:80]
        if not title and not content:
            return None

        user = item.get("user") or {}
        status_id = item.get("id") or item.get("status_id") or ""
        target = item.get("target") or ""
        if not target and status_id:
            target = f"/{user.get('id', '')}/{status_id}" if user.get("id") else f"/S/{status_id}"
        url = f"https://xueqiu.com{target}" if str(target).startswith("/") else str(target or "")
        return {
            "title": title,
            "content": content,
            "time": self._created_at(item.get("created_at") or item.get("timeBefore")),
            "source": f"xueqiu:{user.get('screen_name', '')}".rstrip(":"),
            "url": url,
        }

    async def get_news(
        self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 20
    ) -> Optional[list[dict]]:
        xq_symbol = self._to_xueqiu_symbol(symbol)
        try:
            data = await asyncio.to_thread(self._fetch_statuses, xq_symbol, limit)
        except Exception as e:
            logger.warning("Xueqiu news failed for %s; falling back: %s", xq_symbol, e)
            return None

        items = data.get("list") or data.get("statuses") or []
        results = []
        for item in items:
            if isinstance(item.get("data"), str):
                try:
                    item = json.loads(item["data"])
                except json.JSONDecodeError:
                    continue
            if not isinstance(item, dict):
                continue
            article = self._normalise_status(item)
            if article:
                results.append(article)
        logger.info("Xueqiu news normalized symbol=%s items=%s", xq_symbol, len(results))
        return results[:limit]
