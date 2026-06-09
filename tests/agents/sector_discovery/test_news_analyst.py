import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.sector_discovery.scanners.news_analyst import NewsAnalyst, NewsAnalysis
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, test_mode=True)


@pytest.fixture
def analyst(settings):
    mock_cache = MagicMock()
    mock_collector = MagicMock()
    return NewsAnalyst(settings, mock_cache, mock_collector)


@pytest.mark.asyncio
async def test_news_analyst_extracts_signals(analyst):
    news_items = [
        {"title": "国产光刻机重大突破", "content": "技术突破将带动半导体设备需求", "source": "财联社", "time": "2026-06-02"},
    ]
    analyst.collector.get_global_news = AsyncMock(return_value=news_items)

    mock_analysis = MagicMock()
    mock_analysis.signals = [
        MagicMock(
            theme="半导体设备国产替代",
            sentiment="positive",
            related_sectors=["半导体", "光刻机"],
            catalyst_strength=8.5,
            time_window="medium",
            source_headline="国产光刻机重大突破",
            reasoning="技术突破带动上游设备需求",
        )
    ]

    with patch("src.agents.sector_discovery.scanners.news_analyst.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_analysis
        result = await analyst.scan()

    assert len(result) == 1
    assert result[0].theme == "半导体设备国产替代"
    assert result[0].catalyst_strength == 8.5


@pytest.mark.asyncio
async def test_news_analyst_empty_when_no_news(analyst):
    analyst.collector.get_global_news = AsyncMock(return_value=[])

    result = await analyst.scan()

    assert len(result) == 0


def test_news_analysis_accepts_single_legacy_signal_object():
    analysis = NewsAnalysis.model_validate(
        {
            "core_theme": "AI算力需求升温",
            "sentiment": "positive",
            "related_sectors": ["AI算力", "云计算"],
            "catalyst_intensity": 8,
            "time_horizon": "short",
            "reasoning": "多条新闻指向算力需求改善。",
        }
    )

    assert len(analysis.signals) == 1
    assert analysis.signals[0].theme == "AI算力需求升温"
    assert analysis.signals[0].catalyst_strength == 8
    assert analysis.signals[0].time_window == "short"
