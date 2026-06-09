"""SectorRankingScanner — analyze industry/concept board ranking trends.

Fetches current industry and concept board rankings, compares with cached
ranking from previous run, classifies trend for each board.

Output: SectorMomentumSignal[] with trend classification and scores.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.agents.sector_discovery.models import SectorMomentumSignal
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)

_CACHE_KEY = "sector_ranking:last"
_SUDDEN_THRESHOLD = 10  # rank change positions


class SectorRankingScanner:
    """Discover trending up/down industries and concept boards."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def scan(self) -> list[SectorMomentumSignal]:
        """Fetch board rankings, compare with cache, classify trends."""
        # Fetch current boards
        try:
            industry_boards = await self.collector.list_industry_boards(limit=100) or []
            concept_boards = await self.collector.list_concept_boards(limit=100) or []
        except Exception as e:
            logger.warning("SectorRankingScanner: fetch boards failed: %s", e)
            return []

        all_boards = industry_boards + concept_boards
        if not all_boards:
            return []

        # Build current ranking by change_pct
        all_boards_sorted = sorted(
            all_boards,
            key=lambda b: float(b.get("change_pct", 0) or 0),
            reverse=True,
        )
        current_rank: dict[str, int] = {
            b.get("code", ""): i for i, b in enumerate(all_boards_sorted) if b.get("code")
        }

        # Load previous ranking from cache
        prev_rank: dict[str, int] = {}
        try:
            cached = await self.cache.get(_CACHE_KEY)
            if cached:
                prev_rank = json.loads(cached)
        except Exception as e:
            logger.debug("SectorRankingScanner: cache read failed: %s", e)

        # Cache current ranking for next run
        try:
            await self.cache.set(_CACHE_KEY, json.dumps(current_rank))
        except Exception as e:
            logger.debug("SectorRankingScanner: cache write failed: %s", e)

        # Classify trends
        results: list[SectorMomentumSignal] = []
        for board in all_boards_sorted:
            code = board.get("code", "")
            name = board.get("name", "")
            if not code:
                continue

            curr = current_rank.get(code, 999)
            prev = prev_rank.get(code, curr)
            rank_change = prev - curr  # positive = moved up

            trend = self._classify_trend(rank_change, curr)
            score = self._score_from_trend(trend)

            results.append(
                SectorMomentumSignal(
                    board_code=code,
                    name=name,
                    rank_change=rank_change,
                    trend=trend,
                    composite_score=score,
                )
            )

        logger.info("SectorRankingScanner: analyzed %d boards", len(results))
        return results

    def _classify_trend(self, rank_change: int, current_rank: int) -> str:
        """Classify board trend based on rank change."""
        if rank_change > _SUDDEN_THRESHOLD:
            return "sudden_up"
        elif rank_change > 3:
            return "rising"
        elif rank_change < -_SUDDEN_THRESHOLD:
            return "sudden_down"
        elif rank_change < -3:
            return "falling"
        return "stable"

    def _score_from_trend(self, trend: str) -> float:
        """Map trend to composite score 0-10."""
        scores = {
            "sudden_up": 9.0,
            "rising": 7.0,
            "stable": 5.0,
            "falling": 3.0,
            "sudden_down": 1.0,
        }
        return scores.get(trend, 5.0)
