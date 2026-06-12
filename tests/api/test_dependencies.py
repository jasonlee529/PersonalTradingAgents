import pytest
from src.api.dependencies import AppServices


@pytest.mark.asyncio
async def test_app_services_init(test_settings):
    services = AppServices(test_settings)
    await services.init()
    holdings = await services.portfolio.list_holdings()
    assert holdings == []
    local = await services.collector._historical_store.load_kline("603738", "1d")
    assert local is None
    assert services.collector._historical_store is not None


def test_appservices_has_orchestrator(test_settings):
    services = AppServices(test_settings)
    assert hasattr(services, "portfolio_orchestrator")
    assert services.portfolio_orchestrator is not None
