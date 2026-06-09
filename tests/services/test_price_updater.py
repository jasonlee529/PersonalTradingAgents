import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from src.services.price_updater import PriceUpdater


@pytest.mark.asyncio
async def test_refresh_all():
    collector = MagicMock()
    collector.get_quote = AsyncMock(return_value={"price": 150.0})
    portfolio = MagicMock()
    portfolio.list_symbols = AsyncMock(return_value=["AAPL"])
    pos = MagicMock()
    pos.quantity = 100
    pos.avg_cost = Decimal("100")
    portfolio.get_position = AsyncMock(return_value=pos)
    portfolio.set_position = AsyncMock()

    updater = PriceUpdater(collector, portfolio)
    await updater.refresh_all()

    collector.get_quote.assert_called_once_with("AAPL")
