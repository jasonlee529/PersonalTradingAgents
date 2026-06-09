import pytest
from unittest.mock import AsyncMock, MagicMock

from src.portfolio.orchestrator import PortfolioDrivenOrchestrator


@pytest.mark.asyncio
async def test_on_add_logs_and_triggers_analysis_when_enabled():
    mock_analysis = AsyncMock()

    orch = PortfolioDrivenOrchestrator(
        settings=MagicMock(wiki_auto_analysis_enabled=True),
        analysis_pipeline=mock_analysis,
    )

    await orch.on_portfolio_event("added", "000001")

    mock_analysis.run_single.assert_awaited_once_with("000001")


@pytest.mark.asyncio
async def test_on_add_does_not_trigger_analysis_when_disabled():
    mock_analysis = AsyncMock()

    orch = PortfolioDrivenOrchestrator(
        settings=MagicMock(wiki_auto_analysis_enabled=False),
        analysis_pipeline=mock_analysis,
    )

    await orch.on_portfolio_event("added", "000001")

    mock_analysis.run_single.assert_not_awaited()


@pytest.mark.asyncio
async def test_on_remove_logs_removal():
    orch = PortfolioDrivenOrchestrator(
        settings=MagicMock(),
        analysis_pipeline=None,
    )

    # Should not raise
    await orch.on_portfolio_event("removed", "000001")


@pytest.mark.asyncio
async def test_on_unknown_event_is_noop():
    orch = PortfolioDrivenOrchestrator(
        settings=MagicMock(),
        analysis_pipeline=None,
    )

    # Should not raise
    await orch.on_portfolio_event("unknown", "000001")
