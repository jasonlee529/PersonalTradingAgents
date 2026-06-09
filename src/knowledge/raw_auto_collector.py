from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Awaitable, Callable

from src.data.collector import DataCollector
from src.knowledge.raw_renderers import (
    render_announcement,
    render_news_article,
    render_research_report,
)
from src.knowledge.raw_store import RawStore
from src.portfolio.manager import PortfolioManager

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _canonical_uri(item: dict) -> str:
    return str(item.get("canonical_uri") or item.get("pdf_url") or item.get("url") or "").strip()


def _published_at(item: dict) -> str:
    return str(item.get("published_at") or item.get("time") or item.get("date") or "").strip()


def _source_ref(source_kind: str, symbol: str, item: dict) -> str:
    uri = _canonical_uri(item)
    if uri:
        return _short_hash(uri)
    if source_kind == "announcement":
        identifier = item.get("announcement_id") or item.get("id") or ""
        if identifier:
            return _short_hash(f"{symbol}:{identifier}")
    title = str(item.get("title") or "").strip()
    published_at = _published_at(item)
    if source_kind == "research_report":
        institution = str(item.get("institution") or "").strip()
        return _short_hash(f"{symbol}:{title}:{institution}:{published_at}")
    return _short_hash(f"{symbol}:{title}:{published_at}")


class RawAutoCollector:
    """Best-effort raw collector for holding-related external materials."""

    def __init__(
        self,
        collector: DataCollector,
        raw_store: RawStore,
        portfolio: PortfolioManager,
    ):
        self.collector = collector
        self.raw_store = raw_store
        self.portfolio = portfolio

    async def collect_holding(self, symbol: str, limit: int = 10) -> dict:
        result = {"symbol": symbol}
        result["news_article"] = await self._collect_kind(
            source_kind="news_article",
            symbol=symbol,
            fetch=lambda: self.collector.get_news(symbol, limit=limit),
            render=render_news_article,
            default_provider="eastmoney",
            tag="external/news",
        )
        result["announcement"] = await self._collect_kind(
            source_kind="announcement",
            symbol=symbol,
            fetch=lambda: self.collector.get_announcements(symbol, limit=limit),
            render=render_announcement,
            default_provider="ths",
            tag="external/announcement",
        )
        result["research_report"] = await self._collect_kind(
            source_kind="research_report",
            symbol=symbol,
            fetch=lambda: self.collector.get_research_reports(symbol, limit=limit),
            render=render_research_report,
            default_provider="eastmoney",
            tag="external/research_report",
        )
        return result

    async def collect_portfolio(self, limit_per_symbol: int = 10) -> dict:
        holdings = await self.portfolio.list_holdings()
        results = []
        for holding in holdings:
            try:
                results.append(await self.collect_holding(holding.symbol, limit=limit_per_symbol))
            except Exception as exc:
                logger.warning("Raw collect failed for %s: %s", holding.symbol, exc)
                results.append({"symbol": holding.symbol, "status": "failed"})
        return {"symbols_processed": len(holdings), "results": results}

    async def _collect_kind(
        self,
        *,
        source_kind: str,
        symbol: str,
        fetch: Callable[[], Awaitable[list[dict] | None]],
        render: Callable[[str, dict], str],
        default_provider: str,
        tag: str,
    ) -> dict:
        try:
            items = await fetch()
        except Exception as exc:
            logger.info("Raw %s collect failed for %s: %s", source_kind, symbol, exc)
            return {"saved": 0, "skipped": 0, "status": "failed"}

        if not items:
            return {"saved": 0, "skipped": 0, "status": "empty"}

        saved = 0
        skipped = 0
        captured_at = _now_iso()
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            provider = str(item.get("provider") or item.get("source") or default_provider).strip()
            source_ref = _source_ref(source_kind, symbol, item)
            existing = await self.raw_store.find_by_source_ref(
                source_kind=source_kind,
                source_ref=source_ref,
                symbol=symbol,
            )
            if existing:
                skipped += 1
                continue

            published_at = _published_at(item)
            uri = _canonical_uri(item)
            markdown = render(symbol, {**item, "provider": provider, "canonical_uri": uri})
            metadata = {
                "symbol": symbol,
                "symbols": [symbol],
                "provider": provider,
                "canonical_uri": uri,
                "source_ref": source_ref,
                "published_at": published_at,
                "captured_at": captured_at,
                "tags": [f"stock/{symbol}", tag],
                **item,
            }
            try:
                added = await self.raw_store.add_source(
                    source_kind=source_kind,
                    origin="external",
                    title=title,
                    markdown=markdown,
                    metadata=metadata,
                )
                if added.get("duplicate"):
                    skipped += 1
                else:
                    saved += 1
            except Exception as exc:
                logger.info("Raw %s save skipped for %s: %s", source_kind, symbol, exc)
                skipped += 1

        status = "ok" if saved else "empty"
        return {"saved": saved, "skipped": skipped, "status": status}
