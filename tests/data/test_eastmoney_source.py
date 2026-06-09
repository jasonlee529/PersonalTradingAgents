import pytest
from unittest.mock import patch


@pytest.fixture
def eastmoney():
    from src.data.sources.eastmoney_source import EastmoneySource
    return EastmoneySource()


@pytest.mark.asyncio
async def test_list_concept_boards(eastmoney):
    """Should return concept boards with code, name, change_pct."""
    with patch("src.data.sources.eastmoney_source.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": {
                "diff": [
                    {"f12": "BK1033", "f14": "固态电池", "f3": 5.23},
                    {"f12": "BK1034", "f14": "低空经济", "f3": -1.50},
                ]
            }
        }
        result = await eastmoney.list_concept_boards()
        assert len(result) == 2
        assert result[0]["code"] == "BK1033"
        assert result[0]["name"] == "固态电池"
        assert result[0]["change_pct"] == 5.23


@pytest.mark.asyncio
async def test_list_industry_boards(eastmoney):
    """Should return industry boards with code, name, change_pct."""
    with patch("src.data.sources.eastmoney_source.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": {
                "diff": [
                    {"f12": "BK0428", "f14": "电力行业", "f3": 2.10},
                ]
            }
        }
        result = await eastmoney.list_industry_boards()
        assert len(result) == 1
        assert result[0]["code"] == "BK0428"
        assert result[0]["name"] == "电力行业"


@pytest.mark.asyncio
async def test_get_board_stocks(eastmoney):
    """Should return stocks in a specific board."""
    with patch("src.data.sources.eastmoney_source.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {
            "data": {
                "diff": [
                    {"f12": "300750", "f14": "宁德时代", "f2": 210.50, "f3": 3.25},
                    {"f12": "002594", "f14": "比亚迪", "f2": 245.00, "f3": 1.80},
                ]
            }
        }
        result = await eastmoney.get_board_stocks("BK1033")
        assert len(result) == 2
        assert result[0]["symbol"] == "300750"
        assert result[0]["name"] == "宁德时代"
        assert result[0]["price"] == 210.50
        assert result[0]["change_pct"] == 3.25


@pytest.mark.asyncio
async def test_get_board_stocks_empty_on_error(eastmoney):
    """Should return None on API failure."""
    with patch("src.data.sources.eastmoney_source.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"data": None}
        result = await eastmoney.get_board_stocks("BK9999")
        assert result is None
