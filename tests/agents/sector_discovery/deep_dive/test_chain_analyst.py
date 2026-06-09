import pytest
from unittest.mock import MagicMock

from src.agents.sector_discovery.deep_dive.chain_analyst import ChainAnalyst
from src.agents.sector_discovery.models import SelectedDirection, DirectionContext


class TestChainAnalyst:
    @pytest.fixture
    def agent(self):
        return ChainAnalyst(MagicMock(), MagicMock(), MagicMock())

    @pytest.fixture
    def direction(self):
        return SelectedDirection(
            name="固态电池",
            rank=1,
            total_score=8.7,
        )

    @pytest.mark.asyncio
    async def test_analyze_returns_report(self, agent, direction):
        context = DirectionContext(date="2026-06-04")
        report = await agent.analyze(direction, context)

        assert report.direction_name == "固态电池"
        assert len(report.segments) > 0
        assert report.top_segment
        assert report.diffusion_path

    @pytest.mark.asyncio
    async def test_segments_have_positions(self, agent, direction):
        context = DirectionContext(date="2026-06-04")
        report = await agent.analyze(direction, context)

        positions = [s.position for s in report.segments]
        assert "upstream" in positions or "midstream" in positions
