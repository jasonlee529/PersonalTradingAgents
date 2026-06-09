"""Tests for NewsCollector integration with Cninfo and Eastmoney."""

import pytest
from unittest.mock import AsyncMock

from src.news.collector import NewsCollector
from src.news.models import Announcement, ResearchReport


@pytest.fixture
async def collector(test_settings):
    from src.data.cache import DataCache
    from src.portfolio.manager import PortfolioManager
    cache = DataCache(test_settings)
    await cache.init_db()
    portfolio = PortfolioManager(test_settings)
    c = NewsCollector(test_settings, cache, portfolio)
    return c


@pytest.mark.asyncio
async def test_get_announcements_from_cninfo(collector):
    collector._data_collector.get_announcements = AsyncMock(return_value=[
        {
            "title": "2024年度报告",
            "time": "2025-04-15 18:30:00",
            "pdf_url": "http://static.cninfo.com.cn/finalpage/2025-04-15/12345.PDF",
        },
        {
            "title": "关于对外投资的公告",
            "time": "2025-05-01",
            "pdf_url": "",
        },
    ])

    result = await collector.get_announcements("600519", limit=5)

    assert len(result) == 2
    assert isinstance(result[0], Announcement)
    assert result[0].title == "2024年度报告"
    assert result[0].published_at == "2025-04-15 18:30:00"
    assert result[0].url == "http://static.cninfo.com.cn/finalpage/2025-04-15/12345.PDF"
    assert result[0].relevance_score == 1.0
    assert result[1].title == "关于对外投资的公告"
    assert result[1].url == ""

    # Verify caching
    cached = await collector.cache.get("announcements:600519:5")
    assert cached is not None
    assert len(cached) == 2


@pytest.mark.asyncio
async def test_get_announcements_empty(collector):
    collector._data_collector.get_announcements = AsyncMock(return_value=[])

    result = await collector.get_announcements("600519")
    assert result == []


@pytest.mark.asyncio
async def test_get_announcements_none(collector):
    collector._data_collector.get_announcements = AsyncMock(return_value=None)

    result = await collector.get_announcements("600519")
    assert result == []


@pytest.mark.asyncio
async def test_get_research_reports_from_eastmoney(collector):
    collector._data_collector.get_research_reports = AsyncMock(return_value=[
        {
            "title": "平安银行深度报告",
            "org_name": "中信证券",
            "rating": "买入",
            "publish_date": "2025-05-20 00:00:00.000",
            "pdf_url": "https://pdf.dfcfw.com/pdf/H3_AP20250520_1.pdf",
            "predict_this_year_eps": "2.5",
            "predict_this_year_pe": "5.2",
            "predict_next_year_eps": "2.8",
        },
        {
            "title": "季度点评",
            "org_name": "华泰证券",
            "rating": "增持",
            "publish_date": "2025-04-01",
            "pdf_url": "",
            "predict_this_year_eps": None,
            "predict_this_year_pe": None,
        },
    ])

    result = await collector.get_research_reports("000001", limit=5)

    assert len(result) == 2
    assert isinstance(result[0], ResearchReport)
    assert result[0].title == "平安银行深度报告"
    assert result[0].institution == "中信证券"
    assert result[0].rating == "买入"
    assert result[0].published_at == "2025-05-20 00:00:00.000"
    assert result[0].url == "https://pdf.dfcfw.com/pdf/H3_AP20250520_1.pdf"
    assert result[0].target_price == "13.0"  # 2.5 * 5.2
    assert result[0].predict_this_year_eps == "2.5"
    assert result[0].predict_next_year_eps == "2.8"

    assert result[1].title == "季度点评"
    assert result[1].target_price == ""  # No EPS/PE

    # Verify caching
    cached = await collector.cache.get("research_reports:000001:5")
    assert cached is not None
    assert len(cached) == 2


@pytest.mark.asyncio
async def test_get_research_reports_empty(collector):
    collector._data_collector.get_research_reports = AsyncMock(return_value=[])

    result = await collector.get_research_reports("000001")
    assert result == []


@pytest.mark.asyncio
async def test_get_research_reports_none(collector):
    collector._data_collector.get_research_reports = AsyncMock(return_value=None)

    result = await collector.get_research_reports("000001")
    assert result == []


@pytest.mark.asyncio
async def test_get_combined_feed(collector):
    collector._data_collector.get_announcements = AsyncMock(return_value=[
        {"title": "年报", "time": "2025-01-01", "pdf_url": ""},
    ])
    collector._data_collector.get_research_reports = AsyncMock(return_value=[
        {"title": "研报", "org_name": "A券商", "rating": "买入", "publish_date": "2025-02-01", "pdf_url": ""},
    ])
    collector.get_news = AsyncMock(return_value=[])

    feed = await collector.get_combined_feed("000001")

    assert feed["symbol"] == "000001"
    assert len(feed["announcements"]) == 1
    assert feed["announcements"][0].title == "年报"
    assert len(feed["research_reports"]) == 1
    assert feed["research_reports"][0].title == "研报"
