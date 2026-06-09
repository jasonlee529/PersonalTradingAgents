"""Tests for StockScreener."""

import pytest

from src.agents.sector_discovery.models import SectorSnapshot, StockSignal
from src.agents.sector_discovery.screener import StockScreener


@pytest.fixture
def screener():
    return StockScreener()


def test_screen_empty(screener):
    result = screener.screen([])
    assert result == []


def test_screen_market_heat_threshold(screener):
    snap = SectorSnapshot(
        board_code="BK001",
        name="固态电池",
        tags=["热点追逐"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=9.0, time_horizon="short"),
            StockSignal(symbol="000002", name="B", score=7.5, time_horizon="short"),
            StockSignal(symbol="000003", name="C", score=5.0, time_horizon="short"),
        ],
    )
    result = screener.screen([snap])
    assert len(result) == 1
    # 热点追逐 threshold=7, so only A and B pass
    assert len(result[0].top_stocks) == 2
    assert result[0].top_stocks[0].symbol == "000001"
    assert result[0].top_stocks[1].symbol == "000002"


def test_screen_market_heat_limit(screener):
    snap = SectorSnapshot(
        board_code="BK001",
        name="固态电池",
        tags=["热点追逐"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=9.0, time_horizon="short"),
            StockSignal(symbol="000002", name="B", score=8.0, time_horizon="short"),
            StockSignal(symbol="000003", name="C", score=8.5, time_horizon="short"),
            StockSignal(symbol="000004", name="D", score=7.5, time_horizon="short"),
        ],
    )
    result = screener.screen([snap])
    # 热点追逐 limit=3
    assert len(result[0].top_stocks) == 3


def test_screen_policy_forward_lower_threshold(screener):
    snap = SectorSnapshot(
        board_code="BK002",
        name="商业航天",
        tags=["政策前瞻"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=6.0, time_horizon="medium"),
            StockSignal(symbol="000002", name="B", score=4.0, time_horizon="medium"),
        ],
    )
    result = screener.screen([snap])
    # 政策前瞻 threshold=5, so only A passes
    assert len(result[0].top_stocks) == 1
    assert result[0].top_stocks[0].symbol == "000001"


def test_screen_drops_empty_snapshots(screener):
    snap = SectorSnapshot(
        board_code="BK001",
        name="Empty",
        tags=["热点追逐"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=5.0, time_horizon="short"),
        ],
    )
    result = screener.screen([snap])
    # 热点追逐 threshold=7, A is dropped → snapshot dropped
    assert len(result) == 0


def test_screen_policy_prefers_upstream_and_low_move(screener):
    snap = SectorSnapshot(
        board_code="BK002",
        name="商业航天",
        tags=["政策前瞻"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=6.0, time_horizon="short", metadata={"price_change": 15.0}),
            StockSignal(symbol="000002", name="B", score=6.0, time_horizon="medium", metadata={"position": "upstream", "price_change": 2.0, "policy_level": "部委"}),
        ],
    )
    result = screener.screen([snap])
    # B gets upstream bonus + low move bonus + policy level bonus = higher score
    assert result[0].top_stocks[0].symbol == "000002"
    assert result[0].top_stocks[1].symbol == "000001"


def test_screen_multiple_categories(screener):
    hot = SectorSnapshot(
        board_code="BK001",
        name="热点",
        tags=["热点追逐"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=9.0, time_horizon="short"),
        ],
    )
    policy = SectorSnapshot(
        board_code="BK002",
        name="政策",
        tags=["政策前瞻"],
        top_stocks=[
            StockSignal(symbol="000002", name="B", score=6.0, time_horizon="medium"),
        ],
    )
    result = screener.screen([hot, policy])
    assert len(result) == 2
    assert result[0].tags == ["热点追逐"]
    assert result[1].tags == ["政策前瞻"]


def test_custom_limits_and_thresholds(screener):
    custom = StockScreener(
        limits={"热点追逐": 1},
        thresholds={"热点追逐": 8.0},
    )
    snap = SectorSnapshot(
        board_code="BK001",
        name="固态电池",
        tags=["热点追逐"],
        top_stocks=[
            StockSignal(symbol="000001", name="A", score=9.0, time_horizon="short"),
            StockSignal(symbol="000002", name="B", score=8.5, time_horizon="short"),
        ],
    )
    result = custom.screen([snap])
    assert len(result[0].top_stocks) == 1
    assert result[0].top_stocks[0].symbol == "000001"

