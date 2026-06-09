import pytest

from src.data.sources.tencent_source import TencentSource


@pytest.mark.asyncio
async def test_get_quote_includes_name(monkeypatch):
    source = TencentSource()
    monkeypatch.setattr(
        source,
        "_fetch_quote",
        lambda codes: {
            "300033": {
                "name": "同花顺",
                "price": 210.5,
                "last_close": 208.0,
                "open": 209.0,
                "change_pct": 1.2,
                "high": 212.0,
                "low": 207.5,
                "volume": 123456,
                "turnover": 23456789.0,
                "turnover_pct": 3.4,
                "pe_ttm": 50.0,
                "mcap_yi": 1000.0,
                "float_mcap_yi": 800.0,
                "pb": 8.0,
                "limit_up": 230.0,
                "limit_down": 190.0,
                "pe_static": 45.0,
            }
        },
    )

    result = await source.get_quote("300033")

    assert result["name"] == "同花顺"
    assert result["volume"] == 123456

