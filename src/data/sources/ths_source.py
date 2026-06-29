import asyncio
import csv
import logging
import os
from datetime import datetime
from typing import Optional

import requests

from src.data.sources.base import DataSource
from src.utils.ticker import normalize_ticker

logger = logging.getLogger(__name__)
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class THSSource(DataSource):
    """Tonghuashun (同花顺) APIs: EPS forecast, hot stocks, northbound flow."""

    name = "ths"

    async def get_quote(self, symbol: str) -> Optional[dict]:
        return None

    async def get_kline(self, symbol: str, period: str = "1d", limit: int = 60) -> Optional[list[dict]]:
        return None

    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        return None

    def _fetch_announcements(self, code: str) -> dict:
        url = f"https://basic.10jqka.com.cn/api/stockph/publist/{code}/"
        headers = {
            "User-Agent": _UA,
            "Referer": f"https://basic.10jqka.com.cn/mobile/{code}/pubn.html",
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    async def get_announcements(
        self,
        symbol: str,
        start_date: str = "",
        end_date: str = "",
        category: str = "",
        limit: int = 30,
    ) -> Optional[list[dict]]:
        """Fetch company announcements from Tonghuashun F10."""
        code = str(normalize_ticker(symbol)).zfill(6)
        key = {
            "finance": "finance",
            "financial": "finance",
            "event": "event",
            "major": "event",
            "other": "other",
        }.get(category.lower(), "all")
        try:
            data = await asyncio.to_thread(self._fetch_announcements, code)
            rows = data.get(key) or data.get("all") or []
            results = []
            seen: set[str] = set()
            for item in rows:
                date = str(item.get("date") or "")
                if start_date and date and date < start_date:
                    continue
                if end_date and date and date > end_date:
                    continue
                title = str(item.get("title") or "").strip()
                url = item.get("rawurl") or item.get("url") or ""
                ann_id = str(item.get("guid") or item.get("seq") or url or title)
                if not title or ann_id in seen:
                    continue
                seen.add(ann_id)
                results.append({
                    "title": title,
                    "time": date,
                    "announcement_id": ann_id,
                    "pdf_url": url,
                    "type": item.get("reportname") or item.get("tag") or "",
                    "content": item.get("deatil") or "",
                    "source": self.name,
                })
                if len(results) >= limit:
                    break
            return results
        except Exception as e:
            logger.warning("THS announcements failed for %s: %s", code, e)
            return None

    def _fetch_eps_forecast(self, code: str) -> list[dict]:
        url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
        headers = {"User-Agent": _UA, "Referer": "https://basic.10jqka.com.cn/"}
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
        import pandas as pd
        dfs = pd.read_html(r.text)
        for df in dfs:
            cols = [str(c) for c in df.columns]
            if any("每股收益" in c or "均值" in c for c in cols):
                records = []
                for _, row in df.iterrows():
                    records.append({
                        "year": str(row.iloc[0]) if len(row) > 0 else "",
                        "analysts": int(row.iloc[1]) if len(row) > 1 and str(row.iloc[1]).isdigit() else 0,
                        "min_eps": float(row.iloc[2]) if len(row) > 2 else 0,
                        "mean_eps": float(row.iloc[3]) if len(row) > 3 else 0,
                        "max_eps": float(row.iloc[4]) if len(row) > 4 else 0,
                    })
                return records
        return []

    async def fetch_consensus_expectations(self, symbol: str) -> Optional[dict]:
        code = str(normalize_ticker(symbol)).zfill(6)
        try:
            records = await asyncio.to_thread(self._fetch_eps_forecast, code)
            return {"symbol": code, "forecasts": records, "source": self.name}
        except Exception as e:
            logger.warning("THS profit forecast failed for %s: %s", code, e)
            return None

    async def fetch_market_heatmap(self, date: str = "") -> Optional[list[dict]]:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        try:
            url = f"http://zx.10jqka.com.cn/event/api/getharden/date/{date}/orderby/date/orderway/desc/charset/GBK/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36"}
            r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            d = r.json()
            if d.get("errocode", 0) != 0:
                logger.warning("THS hot stocks API error: %s", d.get("errormsg"))
                return None
            rows = d.get("data") or []
            valid_rows = [row for row in rows if self._is_valid_harden_row(row, date)]
            if rows and not valid_rows:
                logger.warning(
                    "THS hot stocks returned %d rows for %s but none had complete market fields",
                    len(rows), date,
                )
                return None
            return [{
                "code": row.get("code"), "name": row.get("name"),
                "reason": row.get("reason"), "change_pct": row.get("zhangfu"),
                "turnover": row.get("huanshou"), "amount": row.get("chengjiaoe"),
                "dde_net": row.get("ddejingliang"),
                "data_date": row.get("date") or date,
            } for row in valid_rows]
        except Exception as e:
            logger.warning("THS hot stocks failed: %s", e)
            return None

    @staticmethod
    def _is_valid_harden_row(row: dict, requested_date: str) -> bool:
        if str(row.get("date") or requested_date) != requested_date:
            return False
        if not row.get("code") or not row.get("reason"):
            return False
        return any(
            row.get(key) is not None
            for key in ("zhangfu", "huanshou", "chengjiaoe", "ddejingliang", "close")
        )

    def _cache_path(self) -> str:
        from src.config import settings

        cache_dir = settings.runtime_cache_dir / "vendor"
        os.makedirs(cache_dir, exist_ok=True)
        return os.path.join(cache_dir, "northbound_daily.csv")

    def _save_snapshot(self, date_str: str, hgt: float, sgt: float):
        path = self._cache_path()
        existing = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)
                for row in reader:
                    if len(row) >= 3:
                        existing[row[0]] = (row[1], row[2])
        existing[date_str] = (f"{hgt:.2f}", f"{sgt:.2f}")
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "hgt", "sgt"])
            for d in sorted(existing.keys()):
                writer.writerow([d, existing[d][0], existing[d][1]])

    def _load_history(self, n: int = 20) -> list[dict]:
        path = self._cache_path()
        if not os.path.exists(path):
            return []
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 3:
                    try:
                        rows.append({"date": row[0], "hgt": float(row[1]), "sgt": float(row[2])})
                    except ValueError:
                        continue
        return rows[-n:]

    async def fetch_cross_border_flow(self, include_history: bool = False) -> Optional[dict]:
        try:
            url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36", "Host": "data.hexin.cn", "Referer": "https://data.hexin.cn/"}
            r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            d = r.json()
            times = d.get("time", [])
            hgt = d.get("hgt", [])
            sgt = d.get("sgt", [])
            result = {"realtime": [], "source": self.name}
            if times:
                for i in range(max(0, len(times) - 10), len(times)):
                    result["realtime"].append({
                        "time": times[i], "hgt": hgt[i] if i < len(hgt) else None,
                        "sgt": sgt[i] if i < len(sgt) else None,
                    })
                hgt_close = float(hgt[-1]) if hgt else 0
                sgt_close = float(sgt[-1]) if sgt else 0
                result["close"] = {"hgt": hgt_close, "sgt": sgt_close, "total": hgt_close + sgt_close}
                today = datetime.now().strftime("%Y-%m-%d")
                self._save_snapshot(today, hgt_close, sgt_close)
            if include_history:
                result["history"] = self._load_history(20)
            return result
        except Exception as e:
            logger.warning("THS northbound flow failed: %s", e)
            return None

    async def health_check(self) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(requests.get, "https://data.hexin.cn/market/hsgtApi/method/dayChart/", headers={"User-Agent": _UA}, timeout=10),
                timeout=15,
            )
            return True
        except Exception:
            return False

