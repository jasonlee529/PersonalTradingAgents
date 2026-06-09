import logging
from typing import Optional

from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector
from src.news.models import NewsItem, Announcement, ResearchReport
from src.news.relevance import compute_relevance
from src.portfolio.manager import PortfolioManager

logger = logging.getLogger(__name__)


class NewsConceptExtractor:
    """Extract hot concept keywords from news article titles.

    Uses the canonical concept keyword tables from RegexExtractor
    to identify trending themes across a batch of news items.
    """

    def __init__(self):
        # Import here to avoid circular dependency at module load time
        from src.utils.patterns import CONCEPT_KEYWORDS
        self._concept_keywords = CONCEPT_KEYWORDS

    def extract(self, news_items: list[dict]) -> list[str]:
        """Return deduplicated list of concept names found in news titles."""
        found: set[str] = set()
        for item in news_items:
            title = item.get("title", "")
            for keyword, canonical in self._concept_keywords.items():
                if keyword in title and canonical not in found:
                    found.add(canonical)
        return sorted(found)


class NewsCollector:
    """Collect and score news/announcements/reports for portfolio holdings.

    Delegates to DataCollector for multi-source merge (Eastmoney + Sina + CLS),
    then applies relevance scoring and concept extraction.
    """

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        portfolio: PortfolioManager,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.portfolio = portfolio
        self._data_collector = data_collector or DataCollector(settings, cache)

    async def _get_holding_name(self, symbol: str) -> str:
        holdings = await self.portfolio.list_holdings()
        for h in holdings:
            if h.symbol == symbol:
                return h.name
        return ""

    async def get_news(
        self, symbol: str, limit: int = 20, min_relevance: float = 0.0
    ) -> list[NewsItem]:
        key = f"news:{symbol}:{limit}"
        cached = await self.cache.get(key)
        if cached:
            return [NewsItem(**item) for item in cached]

        raw = await self._data_collector.get_news(symbol, limit=limit)
        if not raw:
            return []

        name = await self._get_holding_name(symbol)
        concept_extractor = NewsConceptExtractor()
        concepts = concept_extractor.extract(raw)

        items = []
        for r in raw:
            score = compute_relevance(
                title=r.get("title", ""),
                content=r.get("content", ""),
                symbol=symbol,
                name=name,
            )
            if score >= min_relevance:
                item_concepts = [
                    c for c in concepts
                    if c in r.get("title", "")
                ]
                items.append(NewsItem(
                    title=r["title"],
                    content=r.get("content", ""),
                    source=r.get("source", ""),
                    published_at=r.get("published_at") or r.get("time", ""),
                    url=r.get("url", ""),
                    relevance_score=score,
                    concepts=item_concepts,
                ))

        await self.cache.set(key, [i.model_dump() for i in items], ttl=self.settings.cache_ttl_announcements)
        return items

    async def get_announcements(
        self, symbol: str, limit: int = 10
    ) -> list[Announcement]:
        """Fetch announcements via DataCollector."""
        key = f"announcements:{symbol}:{limit}"
        cached = await self.cache.get(key)
        if cached:
            return [Announcement(**item) for item in cached]

        raw = await self._data_collector.get_announcements(symbol, limit=limit)
        if not raw:
            return []

        items = []
        for r in raw:
            items.append(Announcement(
                title=r.get("title", ""),
                type=r.get("type", ""),
                published_at=r.get("time", ""),
                url=r.get("pdf_url", ""),
                relevance_score=1.0,
            ))

        await self.cache.set(key, [i.model_dump() for i in items], ttl=self.settings.cache_ttl_research_reports)
        return items

    async def get_research_reports(
        self, symbol: str, limit: int = 10
    ) -> list[ResearchReport]:
        """Fetch research reports from Eastmoney via DataCollector."""
        key = f"research_reports:{symbol}:{limit}"
        cached = await self.cache.get(key)
        if cached:
            return [ResearchReport(**item) for item in cached]

        raw = await self._data_collector.get_research_reports(symbol, limit=limit)
        if not raw:
            return []

        items = []
        for r in raw:
            # Build target_price from predicted EPS/PE if available
            target_price = ""
            eps = r.get("predict_this_year_eps")
            pe = r.get("predict_this_year_pe")
            if eps and pe:
                try:
                    target_price = str(round(float(eps) * float(pe), 2))
                except (ValueError, TypeError):
                    pass

            items.append(ResearchReport(
                title=r.get("title", ""),
                institution=r.get("org_name", ""),
                rating=r.get("rating", ""),
                target_price=target_price,
                published_at=r.get("publish_date", ""),
                url=r.get("pdf_url", ""),
                relevance_score=1.0,
                predict_this_year_eps=r.get("predict_this_year_eps"),
                predict_next_year_eps=r.get("predict_next_year_eps"),
            ))

        await self.cache.set(key, [i.model_dump() for i in items], ttl=self.settings.cache_ttl_news)
        return items

    async def get_combined_feed(self, symbol: str) -> dict:
        """Get all news types for a symbol."""
        return {
            "symbol": symbol,
            "news": await self.get_news(symbol),
            "announcements": await self.get_announcements(symbol),
            "research_reports": await self.get_research_reports(symbol),
        }
