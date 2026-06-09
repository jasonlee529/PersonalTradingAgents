import pytest
from unittest.mock import AsyncMock, MagicMock

from src.portfolio.daily_inspection import DailyInspectionJob


@pytest.mark.asyncio
async def test_run_analysis_when_enabled():
    mock_analysis = AsyncMock()
    mock_analysis.run_all.return_value = [MagicMock(symbol="000001"), MagicMock(symbol="000002")]

    job = DailyInspectionJob(
        settings=MagicMock(wiki_auto_analysis_enabled=True),
        analysis_pipeline=mock_analysis,
    )

    result = await job.run()

    mock_analysis.run_all.assert_awaited_once()
    assert result["analysis_ran"] is True
    assert result["analysis"]["jobs_count"] == 2


@pytest.mark.asyncio
async def test_run_skips_when_analysis_disabled():
    job = DailyInspectionJob(
        settings=MagicMock(wiki_auto_analysis_enabled=False),
        analysis_pipeline=None,
    )

    result = await job.run()
    assert result["skipped"] is True


@pytest.mark.asyncio
async def test_run_skips_when_no_pipeline():
    job = DailyInspectionJob(
        settings=MagicMock(wiki_auto_analysis_enabled=True),
        analysis_pipeline=None,
    )

    result = await job.run()
    assert result["skipped"] is True
