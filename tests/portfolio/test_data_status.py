import pytest
from src.portfolio.models import Holding, Market, DataStatus
from src.portfolio.manager import PortfolioManager


@pytest.mark.asyncio
async def test_data_status_default(test_settings):
    mgr = PortfolioManager(test_settings)
    await mgr.init_db()
    await mgr.add_holding(Holding(symbol="TEST", name="Test", market=Market.CN))
    h = await mgr.get_holding("TEST")
    assert h is not None
    assert h.data_status == DataStatus.PENDING


@pytest.mark.asyncio
async def test_update_data_status(test_settings):
    mgr = PortfolioManager(test_settings)
    await mgr.init_db()
    await mgr.add_holding(Holding(symbol="TEST", name="Test", market=Market.CN))
    await mgr.update_data_status("TEST", DataStatus.COLLECTING)
    h = await mgr.get_holding("TEST")
    assert h.data_status == DataStatus.COLLECTING
    await mgr.update_data_status("TEST", DataStatus.READY)
    h = await mgr.get_holding("TEST")
    assert h.data_status == DataStatus.READY


@pytest.mark.asyncio
async def test_get_holding_not_found(test_settings):
    mgr = PortfolioManager(test_settings)
    await mgr.init_db()
    h = await mgr.get_holding("NONEXISTENT")
    assert h is None


@pytest.mark.asyncio
async def test_list_holdings_with_status(test_settings):
    mgr = PortfolioManager(test_settings)
    await mgr.init_db()
    await mgr.add_holding(Holding(symbol="A", name="A", market=Market.CN))
    await mgr.add_holding(Holding(symbol="B", name="B", market=Market.US))
    await mgr.update_data_status("B", DataStatus.READY)
    holdings = await mgr.list_holdings()
    assert len(holdings) == 2
    statuses = {h.symbol: h.data_status for h in holdings}
    assert statuses["A"] == DataStatus.PENDING
    assert statuses["B"] == DataStatus.READY
