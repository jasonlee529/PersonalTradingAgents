"""Tests for EastmoneySource.get_research_reports()."""

import pytest
from unittest.mock import patch, MagicMock

from src.data.sources.eastmoney_source import EastmoneySource


@pytest.fixture
def source():
    return EastmoneySource()


@pytest.mark.asyncio
async def test_get_research_reports_success(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "TotalPage": 2,
        "data": [
            {
                "title": "测试研报标题",
                "stockName": "平安银行",
                "stockCode": "000001",
                "orgSName": "中信证券",
                "publishDate": "2025-05-20 00:00:00.000",
                "infoCode": "AP202505201234567",
                "emRatingName": "买入",
                "indvInduName": "银行",
                "predictThisYearEps": "2.5",
                "predictThisYearPe": "5.2",
                "predictNextYearEps": "2.8",
                "predictNextYearPe": "4.8",
            }
        ],
    }

    with patch("src.data.sources.eastmoney_source.requests.get", return_value=mock_response):
        result = await source.get_research_reports("000001", start_date="2025-01-01", end_date="2025-12-31", limit=5)

    assert result is not None
    assert len(result) == 1
    assert result[0]["title"] == "测试研报标题"
    assert result[0]["stock_name"] == "平安银行"
    assert result[0]["stock_code"] == "000001"
    assert result[0]["org_name"] == "中信证券"
    assert result[0]["publish_date"] == "2025-05-20 00:00:00.000"
    assert result[0]["rating"] == "买入"
    assert result[0]["industry"] == "银行"
    assert result[0]["predict_this_year_eps"] == "2.5"
    assert result[0]["predict_this_year_pe"] == "5.2"
    assert result[0]["pdf_url"] == "https://pdf.dfcfw.com/pdf/H3_AP202505201234567_1.pdf"
    assert result[0]["source"] == "eastmoney"


@pytest.mark.asyncio
async def test_get_research_reports_empty(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {"TotalPage": 0, "data": []}

    with patch("src.data.sources.eastmoney_source.requests.get", return_value=mock_response):
        result = await source.get_research_reports("000001")

    assert result == []


@pytest.mark.asyncio
async def test_get_research_reports_no_pdf_url(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "title": "无PDF",
                "stockName": "A",
                "stockCode": "000001",
                "orgSName": "B证券",
                "publishDate": "2025-01-01",
                "infoCode": "",
                "emRatingName": "",
                "indvInduName": "",
            }
        ]
    }

    with patch("src.data.sources.eastmoney_source.requests.get", return_value=mock_response):
        result = await source.get_research_reports("000001")

    assert result[0]["pdf_url"] == ""


@pytest.mark.asyncio
async def test_get_research_reports_failure(source):
    with patch("src.data.sources.eastmoney_source.requests.get", side_effect=Exception("timeout")):
        result = await source.get_research_reports("000001")

    assert result is None


@pytest.mark.asyncio
async def test_get_research_reports_default_dates(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": []}

    with patch("src.data.sources.eastmoney_source.requests.get", return_value=mock_response) as mock_get:
        await source.get_research_reports("600519")
        call_args = mock_get.call_args
        params = call_args[1]["params"]
        assert "beginTime" in params
        assert "endTime" in params
        assert params["code"] == "600519"


@pytest.mark.asyncio
async def test_get_research_reports_limit(source):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"title": f"Report {i}", "stockName": "A", "stockCode": "000001", "orgSName": "B", "publishDate": "2025-01-01", "infoCode": f"INFO{i}", "emRatingName": "", "indvInduName": ""}
            for i in range(10)
        ]
    }

    with patch("src.data.sources.eastmoney_source.requests.get", return_value=mock_response):
        result = await source.get_research_reports("000001", limit=5)

    assert len(result) == 5
