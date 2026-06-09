"""Tests for CninfoSource."""

import pytest
from unittest.mock import patch, MagicMock

from src.data.sources.cninfo_source import CninfoSource


@pytest.fixture
def source():
    return CninfoSource()


@pytest.mark.asyncio
async def test_get_announcements_success(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "announcements": [
            {
                "announcementId": "12345",
                "announcementTitle": " 2024年度报告 ",
                "announcementTime": "2024-04-15 18:30:00",
                "adjunctUrl": "finalpage/2024-04-15/12345.PDF",
                "columnId": "sse",
            }
        ]
    }

    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response):
        result = await source.get_announcements("600519", start_date="2024-01-01", end_date="2024-12-31")

    assert result is not None
    assert len(result) == 1
    assert result[0]["title"] == "2024年度报告"
    assert result[0]["time"] == "2024-04-15 18:30:00"
    assert result[0]["announcement_id"] == "12345"
    assert result[0]["pdf_url"] == "http://static.cninfo.com.cn/finalpage/2024-04-15/12345.PDF"
    assert result[0]["source"] == "cninfo"


@pytest.mark.asyncio
async def test_get_announcements_empty(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {"announcements": []}

    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response):
        result = await source.get_announcements("600519")

    assert result == []


@pytest.mark.asyncio
async def test_get_announcements_no_adjunct_url(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "announcements": [
            {
                "announcementId": "12345",
                "announcementTitle": "公告",
                "announcementTime": "2024-04-15",
                "adjunctUrl": "",
                "columnId": "sse",
            }
        ]
    }

    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response):
        result = await source.get_announcements("600519")

    assert result[0]["pdf_url"] == ""


@pytest.mark.asyncio
async def test_get_announcements_failure(source):
    with patch("src.data.sources.cninfo_source.requests.post", side_effect=Exception("timeout")):
        result = await source.get_announcements("600519")

    assert result is None


@pytest.mark.asyncio
async def test_get_announcements_default_dates(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {"announcements": []}

    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response) as mock_post:
        await source.get_announcements("600519")
        call_args = mock_post.call_args
        data = call_args[1]["data"]
        assert "seDate" in data
        # Should be a 30-day range ending today
        assert "~" in data["seDate"]


@pytest.mark.asyncio
async def test_sh_exchange_determination(source):
    """600xxx should map to sse column."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"announcements": []}

    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response) as mock_post:
        await source.get_announcements("600519")
        data = mock_post.call_args[1]["data"]
        assert data["column"] == "sse"


@pytest.mark.asyncio
async def test_sz_exchange_determination(source):
    """000xxx / 300xxx should map to szse column."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"announcements": []}

    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response) as mock_post:
        await source.get_announcements("000001")
        data = mock_post.call_args[1]["data"]
        assert data["column"] == "szse"


@pytest.mark.asyncio
async def test_health_check_success(source):
    mock_response = MagicMock()
    with patch("src.data.sources.cninfo_source.requests.post", return_value=mock_response):
        assert await source.health_check() is True


@pytest.mark.asyncio
async def test_health_check_failure(source):
    with patch("src.data.sources.cninfo_source.requests.post", side_effect=Exception("timeout")):
        assert await source.health_check() is False
