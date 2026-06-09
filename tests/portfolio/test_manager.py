# tests/portfolio/test_manager.py
import pytest
from decimal import Decimal
from src.portfolio.manager import PortfolioManager
from src.portfolio.models import Holding


@pytest.fixture
async def manager(test_settings):
    pm = PortfolioManager(test_settings)
    await pm.init_db()
    return pm


@pytest.mark.asyncio
async def test_add_and_list_holdings(manager):
    await manager.add_holding(Holding(symbol="600519", name="贵州茅台", market="CN"))
    await manager.add_holding(Holding(symbol="AAPL", name="Apple", market="US"))
    holdings = await manager.list_holdings()
    assert len(holdings) == 2


@pytest.mark.asyncio
async def test_set_and_get_position(manager):
    await manager.add_holding(Holding(symbol="AAPL", name="Apple", market="US"))
    await manager.set_position("AAPL", quantity=50, avg_cost=Decimal("180.00"))
    pos = await manager.get_position("AAPL")
    assert pos.quantity == 50
    assert pos.avg_cost == Decimal("180.00")


@pytest.mark.asyncio
async def test_remove_holding(manager):
    await manager.add_holding(Holding(symbol="TSLA", name="Tesla", market="US"))
    await manager.remove_holding("TSLA")
    holdings = await manager.list_holdings()
    assert len(holdings) == 0


@pytest.mark.asyncio
async def test_add_holding_notifies_listeners(manager):
    events = []

    async def listener(event_type, symbol):
        events.append((event_type, symbol))

    manager.add_listener(listener)

    await manager.add_holding(Holding(symbol="000001", name="Test", market="CN"))
    assert ("added", "000001") in events

    await manager.remove_holding("000001")
    assert ("removed", "000001") in events

    manager.remove_listener(listener)

    events.clear()
    await manager.add_holding(Holding(symbol="000002", name="Test2", market="CN"))
    assert len(events) == 0
