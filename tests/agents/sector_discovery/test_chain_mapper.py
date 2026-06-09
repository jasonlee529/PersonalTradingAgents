import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.sector_discovery.models import ChainAnalysis, ChainSegment, HotSignal
from src.agents.sector_discovery.policy_miner import PolicySignal
from src.agents.sector_discovery.scanners.chain_mapper import ChainMapper
from src.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, test_mode=True)


@pytest.fixture
def mapper(settings):
    mock_cache = MagicMock()
    mock_collector = MagicMock()
    return ChainMapper(settings, mock_cache, mock_collector)


@pytest.fixture
def hot_signal():
    return HotSignal(
        concept="固态电池",
        heat_level=8.5,
        evidence="5股涨停，资金连续3日流入30亿",
        market_heatmap=["000001", "000002"],
    )


@pytest.fixture
def policy_signals():
    return [
        PolicySignal(
            keyword="固态电池",
            level="部委",
            beneficiary_industries=["锂矿", "电解液", "隔膜"],
            time_window="3-month",
            confidence=0.8,
        )
    ]


@pytest.fixture
def mock_chain_analysis():
    return ChainAnalysis(
        concept="固态电池",
        segments=[
            ChainSegment(
                name="铝塑膜",
                position="upstream",
                expectation_gap_score=9.0,
                reasoning="国产替代率<15%，订单排到2027，但零涨停",
                board_keywords=["铝塑膜", "电池材料"],
            ),
            ChainSegment(
                name="电芯",
                position="midstream",
                expectation_gap_score=4.0,
                reasoning="已有热度，估值偏高",
                board_keywords=["锂电池", "电芯"],
            ),
        ],
        top_segments=["铝塑膜"],
    )


# ── Basic analyze ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chain_mapper_empty_when_no_hot_signals(mapper):
    result = await mapper.analyze([], [])
    assert result == []


@pytest.mark.asyncio
async def test_chain_mapper_finds_upstream_stocks(mapper, hot_signal, policy_signals, mock_chain_analysis):
    mapper.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
        {"code": "BK002", "name": "电池材料"},
    ])
    mapper.collector.get_board_stocks = AsyncMock(side_effect=lambda code, limit: {
        "BK001": [{"symbol": "002466", "name": "天齐锂业", "change_pct": 2.0}],
    }.get(code, []))

    with patch("src.agents.sector_discovery.scanners.chain_mapper.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_chain_analysis
        result = await mapper.analyze([hot_signal], policy_signals)

    assert len(result) >= 1
    # Should only return upstream segments
    upstream = [r for r in result if r.position == "upstream"]
    assert len(upstream) >= 1
    assert upstream[0].concept == "固态电池"
    assert upstream[0].segment_name == "铝塑膜"


@pytest.mark.asyncio
async def test_chain_mapper_skips_high_momentum_upstream(mapper, hot_signal, policy_signals, mock_chain_analysis):
    mapper.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
    ])
    # Upstream stock already up 20% — should be filtered by score < 4.0
    mapper.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "002466", "name": "天齐锂业", "change_pct": 20.0},
    ])

    with patch("src.agents.sector_discovery.scanners.chain_mapper.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_chain_analysis
        result = await mapper.analyze([hot_signal], policy_signals)

    # 9.0 * max(0, 10-20)/10 = 9.0 * 0 = 0 < 4.0, so filtered
    assert result == []


@pytest.mark.asyncio
async def test_chain_mapper_deduplicates_by_concept_segment(mapper, hot_signal, policy_signals, mock_chain_analysis):
    mapper.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
        {"code": "BK002", "name": "电池材料"},
    ])
    mapper.collector.get_board_stocks = AsyncMock(side_effect=lambda code, limit: {
        "BK001": [{"symbol": "002466", "name": "天齐锂业", "change_pct": 2.0}],
        "BK002": [{"symbol": "002466", "name": "天齐锂业", "change_pct": 3.0}],
    }.get(code, []))

    with patch("src.agents.sector_discovery.scanners.chain_mapper.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_chain_analysis
        result = await mapper.analyze([hot_signal], policy_signals)

    # Should deduplicate to single entry per concept+segment
    assert len(result) == 1
    assert result[0].concept == "固态电池"
    assert result[0].segment_name == "铝塑膜"


@pytest.mark.asyncio
async def test_chain_mapper_sorts_by_score(mapper, hot_signal, policy_signals):
    analysis = ChainAnalysis(
        concept="固态电池",
        segments=[
            ChainSegment(
                name="铝塑膜",
                position="upstream",
                expectation_gap_score=9.0,
                reasoning="高预期差",
                board_keywords=["铝塑膜"],
            ),
        ],
        top_segments=["铝塑膜"],
    )
    mapper.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
    ])
    # Two stocks with different price changes
    mapper.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "S1", "name": "股票1", "change_pct": 1.0},
        {"symbol": "S2", "name": "股票2", "change_pct": 5.0},
    ])

    with patch("src.agents.sector_discovery.scanners.chain_mapper.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = analysis
        result = await mapper.analyze([hot_signal], policy_signals)

    # Same segment deduplicated to single entry (highest score wins)
    assert len(result) == 1
    # Lower change_pct = higher score (9.0 * 0.9 > 9.0 * 0.5)
    assert result[0].expectation_gap_score == pytest.approx(8.1, abs=0.1)


@pytest.mark.asyncio
async def test_chain_mapper_builds_policy_context(mapper, hot_signal):
    policy_sigs = [
        PolicySignal(
            keyword="固态电池",
            level="国务院",
            beneficiary_industries=["锂矿", "电解液"],
            time_window="immediate",
            confidence=0.9,
        ),
        PolicySignal(
            keyword="AI算力",
            level="部委",
            beneficiary_industries=["光模块"],
            time_window="3-month",
            confidence=0.7,
        ),
    ]
    ctx = mapper._build_policy_context("固态电池", policy_sigs)
    assert "国务院" in ctx
    assert "锂矿" in ctx
    assert "AI算力" not in ctx  # unrelated policy should be excluded


@pytest.mark.asyncio
async def test_chain_mapper_handles_string_change_pct(mapper, hot_signal, policy_signals, mock_chain_analysis):
    """Eastmoney returns change_pct as string; must not crash on abs('2.5')."""
    mapper.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
    ])
    mapper.collector.get_board_stocks = AsyncMock(return_value=[
        {"symbol": "002466", "name": "天齐锂业", "change_pct": "2.5"},
    ])

    with patch("src.agents.sector_discovery.scanners.chain_mapper.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_chain_analysis
        result = await mapper.analyze([hot_signal], policy_signals)

    assert len(result) == 1
    # 9.0 * max(0, 10-2.5)/10 = 9.0 * 0.75 = 6.75
    assert result[0].expectation_gap_score == pytest.approx(6.75, abs=0.1)


@pytest.mark.asyncio
async def test_chain_mapper_includes_midstream_and_downstream(mapper, hot_signal, policy_signals):
    """ChainMapper should include midstream (主体) and downstream segments, not just upstream."""
    from src.agents.sector_discovery.models import ChainAnalysis, ChainSegment
    analysis = ChainAnalysis(
        concept="固态电池",
        segments=[
            ChainSegment(
                name="铝塑膜", position="upstream",
                expectation_gap_score=9.0, reasoning="高预期差",
                board_keywords=["铝塑膜"],
            ),
            ChainSegment(
                name="电芯制造", position="midstream",
                expectation_gap_score=7.0, reasoning="主体环节",
                board_keywords=["锂电池"],
            ),
            ChainSegment(
                name="电动车", position="downstream",
                expectation_gap_score=5.0, reasoning="应用端",
                board_keywords=["新能源车"],
            ),
        ],
        top_segments=["铝塑膜", "电芯制造"],
    )
    mapper.collector.list_concept_boards = AsyncMock(return_value=[
        {"code": "BK001", "name": "铝塑膜"},
        {"code": "BK002", "name": "锂电池"},
        {"code": "BK003", "name": "新能源车"},
    ])
    mapper.collector.get_board_stocks = AsyncMock(side_effect=lambda code, limit: {
        "BK001": [{"symbol": "S1", "name": "股票1", "change_pct": "2.0"}],
        "BK002": [{"symbol": "S2", "name": "股票2", "change_pct": "3.0"}],
        "BK003": [{"symbol": "S3", "name": "股票3", "change_pct": "4.0"}],
    }.get(code, []))

    with patch("src.agents.sector_discovery.scanners.chain_mapper.llm_structured_output", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = analysis
        result = await mapper.analyze([hot_signal], policy_signals)

    positions = {r.position for r in result}
    assert "upstream" in positions
    assert "midstream" in positions
    assert "downstream" in positions
    # upstream: 9.0 * 0.8 = 7.2 >= 4.0
    # midstream: 7.0 * 0.7 = 4.9 >= 3.5
    # downstream: 5.0 * 0.6 = 3.0 >= 3.0
    assert len(result) == 3

