"""CorrectionScanner — find pullback sectors with fundamental support.

Scans bottom-ranked industry boards for meaningful declines (>5%),
then evaluates constituent stocks for valuation + fundamental quality.
Output: StockSignal with dimension="correction", tag "回调低吸".
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.models import StockSignal
from src.agents.sector_discovery.scanners.base import ScanResult, SectorScanner

logger = logging.getLogger(__name__)

# Thresholds
_MIN_PULLBACK_PCT = 5.0  # board must be down > 5%
_MAX_PE = 30.0
_MAX_PB = 3.0
_MIN_ROE = 0.08


class CorrectionScanner(SectorScanner):
    """Discover pullback opportunities with fundamental support."""

    @property
    def dimension(self) -> str:
        return "correction"

    async def scan(self, board_code: Optional[str] = None) -> ScanResult:
        """Scan for correction opportunities."""
        result = ScanResult(dimension=self.dimension)

        try:
            boards = await self.collector.list_industry_boards(limit=100)
        except Exception as e:
            logger.warning("CorrectionScanner: list_industry_boards failed: %s", e)
            return result

        if not boards:
            return result

        # Sort by change_pct ascending, take bottom decliners
        boards_sorted = sorted(
            boards,
            key=lambda b: float(b.get("change_pct", 0) or 0),
        )
        bottom_boards = [b for b in boards_sorted[:20] if abs(float(b.get("change_pct", 0) or 0)) > _MIN_PULLBACK_PCT]

        logger.info("CorrectionScanner: %d pullback boards found", len(bottom_boards))

        seen_symbols: set[str] = set()

        for board in bottom_boards:
            code = board.get("code", "")
            name = board.get("name", "")
            if not code:
                continue

            try:
                stocks = await self.collector.get_board_stocks(code, limit=10)
            except Exception as e:
                logger.debug("CorrectionScanner: board %s failed: %s", code, e)
                continue

            if not stocks:
                continue

            for item in stocks:
                symbol = item.get("symbol", "")
                stock_name = item.get("name", "")
                if not symbol or symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)

                fundamentals = await self._get_fundamentals(symbol)
                if not fundamentals:
                    continue

                pe = fundamentals.get("pe_ttm", 0.0) or 0.0
                pb = fundamentals.get("pb", 0.0) or 0.0
                roe = fundamentals.get("roe", 0.0) or 0.0
                revenue_growth = fundamentals.get("revenue_growth", 0.0) or 0.0
                debt_ratio = fundamentals.get("debt_ratio", 0.0) or 0.0

                # Fundamental gate
                if pe <= 0 or pe > _MAX_PE:
                    continue
                if pb > _MAX_PB:
                    continue
                if roe < _MIN_ROE:
                    continue

                # Pullback depth as bonus
                board_change = abs(float(board.get("change_pct", 0) or 0))
                pullback_bonus = min(board_change / 10.0, 2.0)

                # Score
                score = 5.0
                score += min((_MAX_PE - pe) / 5.0, 3.0)  # Low PE bonus
                score += min((_MAX_PB - pb) * 2, 2.0)    # Low PB bonus
                score += min(roe * 20, 2.0)              # High ROE bonus
                score += pullback_bonus
                score = min(score, 10.0)

                reason = (
                    f"板块{name}回调{board_change:.1f}%，"
                    f"PE {pe:.1f}，PB {pb:.1f}，ROE {roe*100:.1f}%，"
                    f"基本面支撑，回调低吸机会"
                )

                result.stocks.append(
                    StockSignal(
                        symbol=symbol,
                        name=stock_name or symbol,
                        score=round(score, 1),
                        dimension=self.dimension,
                        reason=reason,
                        time_horizon="medium",
                        metadata={
                            "pe_ttm": pe,
                            "pb": pb,
                            "roe": roe,
                            "revenue_growth": revenue_growth,
                            "debt_ratio": debt_ratio,
                            "board_change_pct": board_change,
                            "board_name": name,
                        },
                    )
                )

        result.stocks.sort(key=lambda s: s.score, reverse=True)
        logger.info("CorrectionScanner: returned %d signals", len(result.stocks))
        return result

    async def _get_fundamentals(self, symbol: str) -> Optional[dict]:
        """Fetch fundamentals for a symbol."""
        try:
            return await self.collector.get_fundamentals(symbol)
        except Exception as e:
            logger.debug("CorrectionScanner: fundamentals failed for %s: %s", symbol, e)
            return None
