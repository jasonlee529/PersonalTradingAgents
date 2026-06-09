"""ValueDigger — board-level value accumulation scanner.

Scans industry and concept boards to find sectors with reasonable valuation
potential (not yet overheated). Operates at board level to avoid the
costly per-stock fundamental queries that caused Scout timeouts.

Logic:
- Fetch industry + concept boards
- Filter out boards that have run up too much (> 20%) or are completely inactive
- Score boards on: recent change moderation, turnover presence, relative position
- Output StockSignal list where each signal represents a board/sector.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.models import StockSignal
from src.agents.sector_discovery.scanners.base import ScanResult, SectorScanner

logger = logging.getLogger(__name__)

# Board-level thresholds
_MAX_CHANGE_PCT = 20.0   # exclude boards that have already surged > 20%
_MIN_CHANGE_PCT = -15.0  # exclude boards that crashed too hard (risk-off)
_MAX_TURNOVER = 1e12     # sanity cap


class ValueDigger(SectorScanner):
    """Discover value accumulation opportunities via board-level screening."""

    @property
    def dimension(self) -> str:
        return "value"

    async def scan(self, board_code: Optional[str] = None) -> ScanResult:
        """Scan boards for value accumulation candidates."""
        result = ScanResult(dimension=self.dimension)

        boards = await self._fetch_boards(board_code)
        if not boards:
            logger.info("ValueDigger: no boards available")
            return result

        logger.info("ValueDigger: evaluating %d boards", len(boards))

        evaluated = 0
        for b in boards:
            code = b.get("code", "")
            name = b.get("name", "")
            if not code or not name:
                continue

            change_pct = float(b.get("change_pct", 0) or 0)
            # turnover may not be present in board list API; default to nonzero
            turnover = float(b.get("turnover", 1e9) or 1e9)

            # Skip overheated or crashed boards
            if change_pct > _MAX_CHANGE_PCT or change_pct < _MIN_CHANGE_PCT:
                continue

            score = self._calculate_score(change_pct, turnover)
            if score <= 0:
                continue

            evaluated += 1
            reason = self._build_reason(change_pct, turnover)

            result.stocks.append(
                StockSignal(
                    symbol=code,
                    name=name,
                    score=round(score, 1),
                    dimension=self.dimension,
                    reason=reason,
                    time_horizon="long",
                    metadata={
                        "change_pct": change_pct,
                        "turnover": turnover,
                        "board_type": b.get("board_type", "industry"),
                    },
                )
            )

        result.stocks.sort(key=lambda s: s.score, reverse=True)
        logger.info(
            "ValueDigger: evaluated %d/%d boards, returned %d signals",
            evaluated, len(boards), len(result.stocks),
        )
        return result

    async def _fetch_boards(self, board_code: Optional[str]) -> list[dict]:
        """Fetch board list. If board_code given, narrow to that board."""
        if board_code and board_code.lower() != "all":
            try:
                stocks = await self.collector.get_board_stocks(board_code, limit=50)
                if stocks:
                    # Return a single pseudo-board for this code
                    return [{"code": board_code, "name": board_code, "change_pct": 0, "turnover": 1}]
            except Exception as e:
                logger.warning("ValueDigger: single board lookup failed: %s", e)

        all_boards: list[dict] = []

        try:
            industries = await self.collector.list_industry_boards(limit=200)
            if industries:
                for b in industries:
                    b["board_type"] = "industry"
                all_boards.extend(industries)
        except Exception as e:
            logger.warning("ValueDigger: industry boards failed: %s", e)

        try:
            concepts = await self.collector.list_concept_boards(limit=200)
            if concepts:
                for b in concepts:
                    b["board_type"] = "concept"
                all_boards.extend(concepts)
        except Exception as e:
            logger.warning("ValueDigger: concept boards failed: %s", e)

        # Deduplicate by code
        seen: set[str] = set()
        deduped: list[dict] = []
        for b in all_boards:
            code = b.get("code", "")
            if code and code not in seen:
                seen.add(code)
                deduped.append(b)

        return deduped

    def _calculate_score(self, change_pct: float, turnover: float) -> float:
        """Score a board for value potential (0-10).

        - Slight decline or flat = higher value potential (not yet run up)
        - Moderate positive change = okay
        - Large positive change = lower score (already discovered)
        - Turnover presence = liquidity confirmation
        """
        score = 0.0

        # Change score: best range is -5% to +5%, penalty outside
        if -5 <= change_pct <= 5:
            score += 4.0
        elif -10 <= change_pct < -5:
            score += 3.0  # dip buying potential
        elif 5 < change_pct <= 10:
            score += 2.0
        elif 10 < change_pct <= 15:
            score += 1.0
        elif 15 < change_pct <= _MAX_CHANGE_PCT:
            score += 0.5
        else:
            return 0.0

        # Turnover score: any meaningful turnover = good
        if turnover > 1e9:
            score += 2.0
        elif turnover > 5e8:
            score += 1.5
        elif turnover > 1e8:
            score += 1.0
        else:
            score += 0.5

        # Volatility moderation bonus: very flat boards get extra value score
        if abs(change_pct) < 2:
            score += 1.5

        return min(score, 10.0)

    def _build_reason(self, change_pct: float, turnover: float) -> str:
        """Build human-readable reason string."""
        parts = [f"板块涨幅 {change_pct:+.2f}%"]
        if turnover > 1e8:
            parts.append(f"成交额 {turnover/1e8:.1f}亿")
        else:
            parts.append("成交活跃度一般")
        if abs(change_pct) < 2:
            parts.append("波动极小，价值蓄势")
        elif change_pct < -5:
            parts.append("阶段性回调，关注修复")
        return "，".join(parts)
