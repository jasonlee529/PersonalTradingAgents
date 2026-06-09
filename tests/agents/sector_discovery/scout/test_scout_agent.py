import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.sector_discovery.llm_utils import SectorDiscoveryLLMError
from src.agents.sector_discovery.scout.scout_agent import ScoutAgent
from src.agents.sector_discovery.models import DirectionContext, HotSignal


class TestScoutAgent:
    @pytest.fixture
    def mock_settings(self):
        return MagicMock()

    @pytest.fixture
    def mock_cache(self):
        return MagicMock()

    @pytest.fixture
    def mock_collector(self):
        collector = MagicMock()
        collector.get_global_news = AsyncMock(return_value=[])
        return collector

    @pytest.fixture
    def agent(self, mock_settings, mock_cache, mock_collector):
        return ScoutAgent(mock_settings, mock_cache, mock_collector)

    @pytest.mark.asyncio
    async def test_scan_returns_candidates(self, agent):
        context = DirectionContext(date="2026-06-04")
        candidates = await agent.scan(context)
        assert isinstance(candidates, list)

    @pytest.mark.asyncio
    async def test_candidate_has_required_fields(self, agent):
        context = DirectionContext(date="2026-06-04")
        candidates = await agent.scan(context)
        if candidates:
            cand = candidates[0]
            assert cand.name
            assert cand.category
            assert 0 <= cand.confidence <= 10

    @pytest.mark.asyncio
    async def test_scan_passes_context_date_to_market_heat(self, agent):
        with patch.object(
            agent, "_scan_market_heat", new=AsyncMock(return_value=[])
        ) as mock_hot, patch.object(
            agent, "_scan_policy", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_fund", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_value", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_news", new=AsyncMock(return_value=[])
        ):
            await agent.scan(DirectionContext(date="2026-06-05"))

        mock_hot.assert_awaited_once_with("2026-06-05")

    @pytest.mark.asyncio
    async def test_scan_keeps_non_llm_candidates_when_news_llm_fails(self, agent):
        with patch.object(
            agent, "_scan_market_heat", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_policy", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_fund", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_value", new=AsyncMock(return_value=[SimpleNamespace(name="低估板块")])
        ), patch.object(
            agent, "_scan_news", new=AsyncMock(side_effect=SectorDiscoveryLLMError("json error"))
        ):
            candidates = await agent.scan(DirectionContext(date="2026-06-09"))

        assert [candidate.name for candidate in candidates] == ["低估板块"]

    @pytest.mark.asyncio
    async def test_scan_raises_llm_error_when_no_other_candidates(self, agent):
        with patch.object(
            agent, "_scan_market_heat", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_policy", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_fund", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_value", new=AsyncMock(return_value=[])
        ), patch.object(
            agent, "_scan_news", new=AsyncMock(side_effect=SectorDiscoveryLLMError("json error"))
        ):
            with pytest.raises(SectorDiscoveryLLMError):
                await agent.scan(DirectionContext(date="2026-06-09"))

    def test_hot_candidates_filter_weak_and_noisy_signals(self, agent):
        signals = [
            HotSignal(
                concept="机器人",
                heat_level=1.2,
                evidence="1股涨停",
                market_heatmap=["603048"],
                order_flow_profile=0.0,
            ),
            HotSignal(
                concept="其他",
                heat_level=8.0,
                evidence="5股涨停",
                market_heatmap=["1", "2", "3", "4", "5"],
                order_flow_profile=0.0,
            ),
            HotSignal(
                concept="AI算力",
                heat_level=4.2,
                evidence="3股涨停",
                market_heatmap=["1", "2", "3"],
                order_flow_profile=0.0,
            ),
            HotSignal(
                concept="半导体",
                heat_level=5.2,
                evidence="1股涨停，资金净流入5亿",
                market_heatmap=["1"],
                order_flow_profile=5e8,
            ),
        ]

        candidates = agent._hot_signals_to_candidates(signals)

        assert [cand.name for cand in candidates] == ["AI算力", "半导体"]
        assert candidates[0].raw_metrics["limit_up_count"] == 3
        assert candidates[1].raw_metrics["order_flow_profile"] == 5e8


