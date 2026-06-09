"""MarketBreadthScanner — compute market breadth and sentiment indicators.

Fetches market statistics and hot stocks to compute:
- Advance/decline ratio
- Limit-up / limit-down counts
- Overall sentiment classification

Output: MarketBreadthContext for report risk warnings.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.models import MarketBreadthContext
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)

# Sentiment thresholds
_OVERHEATED_LIMIT_UP = 100
_OVERHEATED_AD_RATIO = 3.0
_PANIC_LIMIT_DOWN = 50
_PANIC_AD_RATIO = 0.5


class MarketBreadthScanner:
    """Compute market breadth indicators for sentiment assessment."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def scan(self) -> MarketBreadthContext:
        """Fetch market data and compute breadth context."""
        # Market statistics
        up_count = 0
        down_count = 0
        try:
            stats = await self.collector.get_market_statistics()
            if stats:
                up_count = stats.get("up_count", 0) or 0
                down_count = stats.get("down_count", 0) or 0
        except Exception as e:
            logger.warning("MarketBreadthScanner: market stats failed: %s", e)

        # Hot stocks (limit-up proxy)
        limit_up_count = 0
        try:
            market_heatmap = await self.collector.fetch_market_heatmap()
            if market_heatmap:
                limit_up_count = len(market_heatmap)
        except Exception as e:
            logger.debug("MarketBreadthScanner: hot stocks failed: %s", e)

        # Advance/decline ratio
        ad_ratio = (up_count / down_count) if down_count > 0 else float(up_count > 0)

        # Sentiment classification
        if limit_up_count > _OVERHEATED_LIMIT_UP and ad_ratio > _OVERHEATED_AD_RATIO:
            sentiment = "overheated"
            score = 8.0
        elif down_count > _PANIC_LIMIT_DOWN and ad_ratio < _PANIC_AD_RATIO:
            sentiment = "panic"
            score = 2.0
        else:
            sentiment = "neutral"
            # Score based on ad_ratio: 1.0 -> 5.0, 2.0 -> 6.5, 3.0 -> 8.0
            score = min(10.0, max(0.0, 3.0 + ad_ratio * 2.0))

        ctx = MarketBreadthContext(
            advance_decline_ratio=round(ad_ratio, 2),
            limit_up_count=limit_up_count,
            limit_down_count=down_count,  # proxy: use down_count as limit-down proxy
            sentiment=sentiment,
            score=round(score, 1),
        )
        logger.info("MarketBreadthScanner: sentiment=%s score=%.1f", sentiment, score)
        return ctx

