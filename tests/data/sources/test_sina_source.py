import json

from src.data.sources.sina_source import SinaSource


class _Response:
    def __init__(self, rows):
        self.text = json.dumps(rows)

    def raise_for_status(self):
        return None


def test_market_statistics_paginates_all_rows(monkeypatch):
    source = SinaSource()
    first_page = [
        {"symbol": f"sh600{i:03d}", "name": f"A{i}", "changepercent": 1.0, "amount": 100000000}
        for i in range(100)
    ]
    first_page[0]["changepercent"] = 10.0
    first_page[1]["changepercent"] = -1.0
    pages = {
        "1": first_page,
        "2": [
            {"symbol": "sz300001", "name": "C", "changepercent": 20.0, "amount": 300000000},
        ],
        "3": [],
    }

    def fake_get(url, params, headers, timeout):
        return _Response(pages[params["page"]])

    monkeypatch.setattr("src.data.sources.sina_source.requests.get", fake_get)

    result = source._fetch_market_statistics()

    assert result["stock_count"] == 101
    assert result["up_count"] == 100
    assert result["down_count"] == 1
    assert result["limit_up_count"] == 2
    assert result["total_amount"] == 103.0
