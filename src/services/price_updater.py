import logging
from decimal import Decimal
from src.data.collector import DataCollector
from src.portfolio.manager import PortfolioManager

logger = logging.getLogger(__name__)


class PriceUpdater:
    """Refreshes current prices for all portfolio holdings."""

    def __init__(self, collector: DataCollector, portfolio: PortfolioManager):
        self.collector = collector
        self.portfolio = portfolio

    async def refresh_all(self) -> None:
        """Fetch quotes and update positions."""
        symbols = await self.portfolio.list_symbols()
        if not symbols:
            return
        for symbol in symbols:
            try:
                quote = await self.collector.get_quote(symbol)
                if quote and quote.get("price"):
                    price = Decimal(str(quote["price"]))
                    pos = await self.portfolio.get_position(symbol)
                    if not pos:
                        from src.portfolio.models import Position
                        pos = Position(symbol=symbol, quantity=0, avg_cost=Decimal("0"))
                    pos.update_price(price)
                    await self.portfolio.upsert_position(pos)
            except Exception as e:
                logger.warning("Price refresh failed for %s: %s", symbol, e)
