import pytest
from unittest.mock import MagicMock

from src.agents.sector_discovery.deep_dive.catalyst_agent import CatalystAgent
from src.agents.sector_discovery.models import SelectedDirection, DirectionContext


class TestCatalystAgent:
    @pytest.fixture
    def agent(self):
        return CatalystAgent(MagicMock(), MagicMock(), MagicMock())

    @pytest.fixture
    def direction(self):
        return SelectedDirection(name="固态电池", rank=1, total_score=8.7)

    @pytest.mark.asyncio
    async def test_analyze_returns_timeline(self, agent, direction):
        context = DirectionContext(date="2026-06-04")
        timeline = await agent.analyze(direction, context)

        assert timeline.direction_name == "固态电池"
        assert len(timeline.events) > 0
        assert timeline.next_key_event

    @pytest.mark.asyncio
    async def test_events_have_categories(self, agent, direction):
        context = DirectionContext(date="2026-06-04")
        timeline = await agent.analyze(direction, context)

        categories = [e.time_category for e in timeline.events]
        assert "past" in categories or "imminent" in categories
