import pytest

from src.data.sources.ths_source import THSSource


@pytest.mark.asyncio
async def test_get_announcements_from_publist(monkeypatch):
    source = THSSource()
    monkeypatch.setattr(
        source,
        "_fetch_announcements",
        lambda code: {
            "all": [
                {
                    "seq": 58105429,
                    "guid": "f16ea99f093f683d",
                    "title": "同花顺：2026年一季度报告",
                    "date": "2026-04-23",
                    "reportname": "2026年一季报",
                    "deatil": "净利润同比增长",
                    "rawurl": "http://static.cninfo.com.cn/finalpage/2026-04-23/demo.PDF",
                }
            ]
        },
    )

    result = await source.get_announcements("300033", limit=5)

    assert len(result) == 1
    assert result[0]["title"] == "同花顺：2026年一季度报告"
    assert result[0]["type"] == "2026年一季报"
    assert result[0]["pdf_url"].endswith("demo.PDF")
    assert result[0]["source"] == "ths"


@pytest.mark.asyncio
async def test_get_announcements_filters_date(monkeypatch):
    source = THSSource()
    monkeypatch.setattr(
        source,
        "_fetch_announcements",
        lambda code: {
            "all": [
                {"seq": 1, "title": "旧公告", "date": "2026-01-01"},
                {"seq": 2, "title": "新公告", "date": "2026-05-01"},
            ]
        },
    )

    result = await source.get_announcements("300033", start_date="2026-04-01")

    assert [item["title"] for item in result] == ["新公告"]
