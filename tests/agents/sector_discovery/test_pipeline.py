import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.sector_discovery.pipeline import SectorDiscoveryPipeline
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, test_mode=True)


@pytest.fixture
def pipeline(settings):
    mock_cache = MagicMock()
    mock_cache.init_db = AsyncMock()
    return SectorDiscoveryPipeline(settings, mock_cache)


@pytest.mark.asyncio
async def test_pipeline_runs_all_scanners(pipeline):
    """Pipeline should invoke all scanners and produce a report."""
    # Mock all external calls to avoid network
    pipeline.collector.get_global_news = AsyncMock(return_value=[])
    pipeline.collector.get_market_indices = AsyncMock(return_value=[])
    pipeline.collector.get_market_statistics = AsyncMock(return_value={"up_count": 2000, "down_count": 2000})
    pipeline.collector.get_sector_rankings = AsyncMock(return_value=([], []))
    pipeline.collector.fetch_cross_border_flow = AsyncMock(return_value=None)
    pipeline.collector.fetch_market_heatmap = AsyncMock(return_value=[])
    pipeline.collector.list_industry_boards = AsyncMock(return_value=[])
    pipeline.collector.list_concept_boards = AsyncMock(return_value=[])

    with patch("src.agents.sector_discovery.pipeline.PolicyMiner") as MockPM, \
         patch("src.agents.sector_discovery.pipeline.NewsAnalyst") as MockNA, \
         patch("src.agents.sector_discovery.pipeline.MarketHeatScanner") as MockHM, \
         patch("src.agents.sector_discovery.pipeline.ChainMapper") as MockCM, \
         patch("src.agents.sector_discovery.pipeline.FundAnalyst") as MockFA, \
         patch("src.agents.sector_discovery.pipeline.ValueDigger") as MockVD, \
         patch("src.agents.sector_discovery.pipeline.CorrectionScanner") as MockCS, \
         patch("src.agents.sector_discovery.pipeline.SectorRankingScanner") as MockSR, \
         patch("src.agents.sector_discovery.pipeline.PolicyScout") as MockPS, \
         patch("src.agents.sector_discovery.pipeline.MarketBreadthScanner") as MockMB:

        # Set up mocks
        mock_pm = MockPM.return_value
        mock_pm.mine = MagicMock(return_value=[])
        mock_na = MockNA.return_value
        mock_na.scan = AsyncMock(return_value=[])
        mock_hm = MockHM.return_value
        mock_hm.scan = AsyncMock(return_value=[])
        mock_cm = MockCM.return_value
        mock_cm.analyze = AsyncMock(return_value=[])
        mock_fa = MockFA.return_value
        mock_fa.scan = AsyncMock(return_value=MagicMock(stocks=[]))
        mock_vd = MockVD.return_value
        mock_vd.scan = AsyncMock(return_value=MagicMock(stocks=[]))
        mock_cs = MockCS.return_value
        mock_cs.scan = AsyncMock(return_value=MagicMock(stocks=[]))
        mock_sr = MockSR.return_value
        mock_sr.scan = AsyncMock(return_value=[])
        mock_ps = MockPS.return_value
        mock_ps.scan = AsyncMock(return_value=[])
        mock_mb = MockMB.return_value
        mock_mb.scan = AsyncMock(return_value=MagicMock(sentiment="neutral", score=5.0))

        report = await pipeline.run(board_code=None)

    assert report is not None
    assert report.date != ""
    mock_hm.scan.assert_awaited_once_with(trade_date=report.date)


