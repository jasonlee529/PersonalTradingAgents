from src.data.sources.ths_source import THSSource


def test_harden_row_rejects_event_only_payload():
    source = THSSource()

    assert not source._is_valid_harden_row(
        {
            "code": "002730",
            "name": "电光科技",
            "reason": "定增加码算力+矿用防爆电器",
            "date": "2026-06-15",
            "market": 33,
        },
        "2026-06-15",
    )


def test_harden_row_accepts_market_payload():
    source = THSSource()

    assert source._is_valid_harden_row(
        {
            "code": "002730",
            "name": "电光科技",
            "reason": "定增加码算力+矿用防爆电器",
            "date": "2026-06-15",
            "zhangfu": 10.0,
        },
        "2026-06-15",
    )
