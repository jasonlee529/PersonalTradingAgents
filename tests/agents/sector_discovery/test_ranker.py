"""Tests for SectorRanker."""

import pytest

from src.agents.sector_discovery.models import SectorSnapshot
from src.agents.sector_discovery.ranker import DEFAULT_WEIGHTS, SectorRanker


@pytest.fixture
def ranker():
    return SectorRanker()


def test_rank_empty(ranker):
    result = ranker.rank([])
    assert result == []


def test_rank_single_snapshot(ranker):
    snap = SectorSnapshot(
        board_code="BK001",
        name="固态电池",
        tags=["热点追逐"],
        market_heat_score=8.0,
        policy_score=3.0,
        expectation_gap_score=2.0,
    )
    result = ranker.rank([snap])
    assert len(result) == 1
    assert result[0].composite_score > 0


def test_rank_sorts_by_composite_score(ranker):
    low = SectorSnapshot(
        board_code="BK001",
        name="A",
        tags=["热点追逐"],
        market_heat_score=3.0,
    )
    high = SectorSnapshot(
        board_code="BK002",
        name="B",
        tags=["热点追逐"],
        market_heat_score=9.0,
    )
    result = ranker.rank([low, high])
    assert result[0].name == "B"
    assert result[1].name == "A"


def test_rank_limits_top_5_per_category(ranker):
    snaps = [
        SectorSnapshot(
            board_code=f"BK{i:03d}",
            name=f"S{i}",
            tags=["热点追逐"],
            market_heat_score=float(i),
        )
        for i in range(10)
    ]
    result = ranker.rank(snaps)
    assert len(result) == 5
    assert result[0].name == "S9"


def test_rank_multiple_categories(ranker):
    hot = SectorSnapshot(
        board_code="BK001", name="热点A", tags=["热点追逐"], market_heat_score=9.0
    )
    policy = SectorSnapshot(
        board_code="BK002", name="政策B", tags=["政策前瞻"], policy_score=8.0
    )
    result = ranker.rank([hot, policy])
    assert len(result) == 2
    # Market heat should score higher because market_heat_score=9 > policy_score=8
    # and expectation_gap defaults to 0
    assert result[0].name == "热点A"


def test_rank_custom_weights(ranker):
    # With custom weights that zero out everything, score should be 0
    zero_weights = {k: 0.0 for k in DEFAULT_WEIGHTS}
    custom_ranker = SectorRanker(weights=zero_weights)
    snap = SectorSnapshot(
        board_code="BK001", name="A", tags=["热点追逐"], market_heat_score=9.0
    )
    result = custom_ranker.rank([snap])
    assert result[0].composite_score == 0.0


def test_expectation_gap_boosts_score(ranker):
    low_gap = SectorSnapshot(
        board_code="BK001",
        name="LowGap",
        tags=["政策前瞻"],
        market_heat_score=5.0,
        policy_score=5.0,
        expectation_gap_score=2.0,
    )
    high_gap = SectorSnapshot(
        board_code="BK002",
        name="HighGap",
        tags=["政策前瞻"],
        market_heat_score=5.0,
        policy_score=5.0,
        expectation_gap_score=9.0,
    )
    result = ranker.rank([low_gap, high_gap])
    assert result[0].name == "HighGap"
    assert result[0].composite_score > result[1].composite_score

