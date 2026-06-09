"""FundAnalyst — institutional mismatch dimension.

Identifies stocks where funds have newly entered or increased positions,
but the stock price hasn't moved much yet (market hasn't recognized).

Input: FundHoldingsStore (new holdings + hold ratios)
Processing:
  1. Fetch new/increased fund holdings
  2. Get recent price change (20-day)
  3. Filter: price change < threshold (e.g. 10%)
  4. Boost score for star fund managers
Output: StockSignal list with fund dimension.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.models import StockSignal
from src.agents.sector_discovery.scanners.base import ScanResult, SectorScanner
from src.config import Settings
from src.data.fund_holdings_store import FundHoldingsStore

logger = logging.getLogger(__name__)

# Default star fund managers (fund code prefix or full code)
# Users can override via settings.star_fund_managers
DEFAULT_STAR_FUNDS: set[str] = {
    "110022",  # 易方达消费
    "000083",  # 汇添富消费
    "163406",  # 兴全合润
    "001938",  # 中欧时代先锋
    "005911",  # 广发双擎升级
    "008314",  # 上投摩根新兴动力
    "002190",  # 农银新能源主题
    "001475",  # 易方达国防军工
    "005827",  # 易方达蓝筹精选
    "007119",  # 睿远成长价值
}

# Star fund code → manager name mapping
STAR_FUND_MANAGERS: dict[str, str] = {
    "110022": "萧楠",
    "000083": "胡昕炜",
    "163406": "谢治宇",
    "001938": "周应波",
    "005911": "刘格菘",
    "008314": "杜猛",
    "002190": "邢军亮",
    "001475": "何崇恺",
    "005827": "张坤",
    "007119": "傅鹏博",
}

# Price movement threshold: if stock moved > this, skip (already recognized)
_DEFAULT_PRICE_CHANGE_THRESHOLD = 10.0


class FundAnalyst(SectorScanner):
    """Discover institutional mismatch opportunities.

    Core insight: fund Q2 newly entered a stock, but price still flat.
    Market hasn't caught up yet → medium-term opportunity.
    """

    def __init__(
        self,
        settings: Settings,
        cache,
        data_collector=None,
        store: Optional[FundHoldingsStore] = None,
    ):
        super().__init__(settings, cache, data_collector)
        self.store = store or FundHoldingsStore(settings)
        self.star_funds: set[str] = set(
            getattr(settings, "star_fund_managers", list(DEFAULT_STAR_FUNDS))
        )
        self.price_threshold = getattr(
            settings, "fund_analyst_price_threshold", _DEFAULT_PRICE_CHANGE_THRESHOLD
        )

    @property
    def dimension(self) -> str:
        return "fund"

    async def scan(self, board_code: Optional[str] = None) -> ScanResult:
        """Scan for institutional mismatch stocks."""
        result = ScanResult(dimension=self.dimension)

        await self.store.init_db()

        # 1. Get new holdings (is_new=1) for latest period
        try:
            new_holdings = await self.store.get_new_holdings(min_hold_ratio=0.5)
        except Exception as e:
            logger.warning("FundAnalyst: failed to fetch new holdings: %s", e)
            return result

        if not new_holdings:
            logger.info("FundAnalyst: no new fund holdings found")
            return result

        logger.info("FundAnalyst: %d new holdings to evaluate", len(new_holdings))

        # Group by symbol and aggregate metrics
        symbol_map: dict[str, dict] = {}
        for h in new_holdings:
            symbol = h.get("symbol", "")
            if not symbol:
                continue
            if symbol not in symbol_map:
                symbol_map[symbol] = {
                    "name": "",
                    "total_ratio": 0.0,
                    "fund_count": 0,
                    "star_count": 0,
                    "star_names": [],
                }
            symbol_map[symbol]["total_ratio"] += h.get("hold_ratio", 0.0)
            symbol_map[symbol]["fund_count"] += 1

            fund_code = h.get("fund_code", "")
            fund_name = h.get("fund_name", "")
            # Check star fund (match by prefix or exact code)
            code_base = fund_code.split(".")[0] if "." in fund_code else fund_code
            if code_base in self.star_funds:
                symbol_map[symbol]["star_count"] += 1
                manager_name = STAR_FUND_MANAGERS.get(code_base, "")
                display_name = f"{manager_name}({fund_name})" if manager_name else fund_name
                if display_name:
                    symbol_map[symbol]["star_names"].append(display_name)

        # 2. Evaluate price movement for each candidate
        evaluated = 0
        for symbol, data in symbol_map.items():
            # Skip if too many funds already (might be over-owned)
            if data["fund_count"] > 20:
                continue

            price_change = await self._get_price_change(symbol)
            if price_change is None:
                # No price data — include with lower confidence
                price_change = 0.0

            # Core filter: fund entered but price hasn't moved much
            if price_change > self.price_threshold:
                continue

            evaluated += 1

            # Score calculation
            # Base: total hold ratio (0-5)
            base_score = min(data["total_ratio"] * 2, 5.0)
            # Bonus: star manager (0-3)
            star_bonus = min(data["star_count"] * 1.5, 3.0)
            # Bonus: low price movement = more mismatch (0-2)
            mismatch_bonus = max(0, 2.0 - price_change / 5.0)

            score = round(base_score + star_bonus + mismatch_bonus, 1)
            score = min(score, 10.0)

            reason_parts = [
                f"Q2新增{data['fund_count']}只基金持仓",
                f"合计占股票市值比 {data['total_ratio']:.1f}%",
            ]
            if data["star_names"]:
                reason_parts.append(f"明星基金经理: {', '.join(data['star_names'][:2])}")
            if price_change > 0:
                reason_parts.append(f"近20日涨幅仅 {price_change:.1f}%")
            else:
                reason_parts.append("近20日股价未涨")

            result.stocks.append(
                StockSignal(
                    symbol=symbol,
                    name=data["name"] or symbol,
                    score=score,
                    dimension=self.dimension,
                    reason="；".join(reason_parts),
                    time_horizon="medium",
                    metadata={
                        "fund_count": data["fund_count"],
                        "star_count": data["star_count"],
                        "total_ratio": data["total_ratio"],
                        "price_change": price_change,
                        "is_fund_new": True,
                    },
                )
            )

        # Sort by score desc
        result.stocks.sort(key=lambda s: s.score, reverse=True)
        logger.info(
            "FundAnalyst: evaluated %d/%d symbols, returned %d signals",
            evaluated, len(symbol_map), len(result.stocks),
        )
        return result

    async def _get_price_change(self, symbol: str) -> Optional[float]:
        """Get 20-day price change percentage. Returns None if unavailable."""
        try:
            quote = await self.collector.get_quote(symbol)
            if quote:
                change_pct = quote.get("change_pct")
                if change_pct is not None:
                    return float(change_pct)
        except Exception as e:
            logger.debug("FundAnalyst: quote failed for %s: %s", symbol, e)

        # Fallback: kline last 20 days
        try:
            kline = await self.collector.get_kline(symbol, period="1d", limit=20)
            if kline and len(kline) >= 2:
                first = kline[0].get("close", 0)
                last = kline[-1].get("close", 0)
                if first and last:
                    return round((last - first) / first * 100, 2)
        except Exception as e:
            logger.debug("FundAnalyst: kline failed for %s: %s", symbol, e)

        return None
