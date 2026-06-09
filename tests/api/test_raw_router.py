def test_raw_manual_source_roundtrip(api_client):
    resp = api_client.post(
        "/api/raw/sources",
        json={
            "source_kind": "manual_source",
            "origin": "user",
            "title": "手动材料",
            "markdown": "# 手动材料\n\n正文",
            "metadata": {
                "manual_subtype": "article",
                "symbols": ["603738"],
                "tags": ["manual/article", "stock/603738"],
            },
        },
    )
    assert resp.status_code == 200
    source = resp.json()
    assert source["source_kind"] == "manual_source"

    list_resp = api_client.get("/api/raw/sources", params={"source_kind": "manual_source", "symbol": "603738"})
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    detail_resp = api_client.get(f"/api/raw/sources/{source['source_id']}")
    assert detail_resp.status_code == 200
    assert "正文" in detail_resp.json()["markdown"]

    verify_resp = api_client.post(f"/api/raw/sources/{source['source_id']}/verify")
    assert verify_resp.status_code == 200


def test_raw_trade_log_updates_position(api_client):
    resp = api_client.post(
        "/api/raw/trade-log",
        json={
            "trade_date": "2026-06-04",
            "entries": [
                {
                    "symbol": "603738",
                    "name": "测试",
                    "action": "buy",
                    "quantity": 1000,
                    "price": 12.3,
                    "commission": 5,
                    "tax": 0,
                    "other_fees": 0,
                    "reason": "测试",
                    "linked_source_ids": [],
                }
            ],
            "position_overrides": [
                {
                    "symbol": "603738",
                    "final_quantity": 1000,
                    "final_avg_cost": 12.305,
                    "final_current_price": 12.3,
                    "override_reason": "",
                }
            ],
        },
    )
    assert resp.status_code == 200
    source_id = resp.json()["source"]["source_id"]
    assert source_id.startswith("daily_trade_log:")

    log_resp = api_client.get("/api/raw/trade-log", params={"date": "2026-06-04"})
    assert log_resp.status_code == 200
    assert log_resp.json()["source"]["source_id"] == source_id

    portfolio_resp = api_client.get("/api/portfolio/holdings")
    assert portfolio_resp.status_code == 200
