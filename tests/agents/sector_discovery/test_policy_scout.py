import pytest
from unittest.mock import AsyncMock

from src.agents.sector_discovery.models import ChainSignal
from src.agents.sector_discovery.policy_miner import PolicySignal
from src.agents.sector_discovery.scanners.policy_scout import PolicyScout


@pytest.fixture
async def policy_scanner(test_settings):
    from src.data.cache import DataCache
    cache = DataCache(test_settings)
    await cache.init_db()
    scanner = PolicyScout(test_settings, cache)
    return scanner


@pytest.fixture
def policy_signals():
    return [
        PolicySignal(
            keyword="固态电池",
            level="部委",
            beneficiary_industries=["铝塑膜", "电池材料", "隔膜"],
            time_window="3-month",
            confidence=0.8,
        ),
        PolicySignal(
            keyword="AI算力",
            level="国务院",
            beneficiary_industries=["光模块", "服务器"],
            time_window="annual",
            confidence=0.9,
        ),
    ]


@pytest.fixture
def chain_signals():
    return [
        ChainSignal(
            concept="固态电池",
            segment_name="铝塑膜",
            position="upstream",
            expectation_gap_score=9.0,
            reasoning="国产替代率低",
            board_keywords=["铝塑膜", "电池材料"],
        ),
        ChainSignal(
            concept="AI算力",
            segment_name="光模块",
            position="upstream",
            expectation_gap_score=7.5,
            reasoning="800G放量",
            board_keywords=["光模块", "CPO"],
        ),
    ]


@pytest.mark.asyncio
async def test_policy_scout_cross_match_and_finds_stocks(policy_scanner, policy_signals, chain_signals):
    """PolicyScout should cross-match policy + chain signals and find stocks."""
    policy_scanner.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
        {"code": "BK002", "name": "电池材料"},
    ])
    policy_scanner.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "002466", "name": "天齐锂业", "change_pct": 2.0},
        {"symbol": "002709", "name": "天赐材料", "change_pct": 3.0},
    ])

    result = await policy_scanner.scan(policy_signals, chain_signals)
    assert len(result) >= 1
    # Should find stocks from matched upstream boards
    symbols = [s.symbol for s in result]
    assert "002466" in symbols or "002709" in symbols


@pytest.mark.asyncio
async def test_policy_scout_empty_when_no_inputs(policy_scanner):
    result = await policy_scanner.scan([], [])
    assert result == []


@pytest.mark.asyncio
async def test_policy_scout_empty_when_no_cross_match(policy_scanner):
    """When policy and chain signals don't match, return empty."""
    policy_sigs = [
        PolicySignal(
            keyword="猪肉",
            level="地方",
            beneficiary_industries=["养殖"],
            time_window="immediate",
            confidence=0.5,
        ),
    ]
    chain_sigs = [
        ChainSignal(
            concept="AI算力",
            segment_name="光模块",
            position="upstream",
            expectation_gap_score=7.0,
            reasoning="...",
            board_keywords=["光模块"],
        ),
    ]
    result = await policy_scanner.scan(policy_sigs, chain_sigs)
    assert result == []


@pytest.mark.asyncio
async def test_policy_scout_skips_high_momentum(policy_scanner, policy_signals, chain_signals):
    """Stocks that already moved >10% should be skipped."""
    policy_scanner.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
    ])
    policy_scanner.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "002466", "name": "天齐锂业", "change_pct": 15.0},  # Too hot
    ])

    result = await policy_scanner.scan(policy_signals, chain_signals)
    assert result == []


@pytest.mark.asyncio
async def test_policy_scout_scores_by_policy_level(policy_scanner, chain_signals):
    """国务院级 policy should score higher than 地方级."""
    high_policy = [
        PolicySignal(
            keyword="AI算力",
            level="国务院",
            beneficiary_industries=["光模块"],
            time_window="annual",
            confidence=0.9,
        ),
    ]
    policy_scanner.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "光模块"},
    ])
    policy_scanner.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "300308", "name": "中际旭创", "change_pct": 2.0},
    ])

    result = await policy_scanner.scan(high_policy, chain_signals)
    assert len(result) >= 1
    assert result[0].score >= 8.0  # 5 base + 3国务院 + 2upstream


@pytest.mark.asyncio
async def test_policy_scout_standalone_without_chain_signals(policy_scanner, policy_signals):
    """PolicyScout should work standalone when chain_signals is empty."""
    policy_scanner.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "半导体设备"},
        {"code": "BK002", "name": "锂电池"},
    ])
    policy_scanner.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "000001", "name": "股票1", "change_pct": "2.0"},
    ])

    result = await policy_scanner.scan(policy_signals, chain_signals=[])

    assert len(result) >= 1
    assert result[0].dimension == "policy"
