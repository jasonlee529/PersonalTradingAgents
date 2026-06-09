from src.agents.sector_discovery.models import NewsSignal, SectorMomentumSignal, MarketBreadthContext


def test_news_signal_creation():
    sig = NewsSignal(
        theme="半导体设备国产替代",
        sentiment="positive",
        related_sectors=["半导体", "光刻机"],
        catalyst_strength=8.5,
        time_window="medium",
        source_headline="国产光刻机突破",
        reasoning="技术突破将带动上游设备需求",
    )
    assert sig.theme == "半导体设备国产替代"
    assert sig.catalyst_strength == 8.5


def test_sector_momentum_signal_creation():
    sig = SectorMomentumSignal(
        board_code="BK001",
        name="半导体",
        rank_change=15,
        trend="sudden_up",
        composite_score=8.5,
    )
    assert sig.trend == "sudden_up"
    assert sig.composite_score == 8.5


def test_market_breadth_context_creation():
    ctx = MarketBreadthContext(
        advance_decline_ratio=2.5,
        limit_up_count=80,
        limit_down_count=5,
        sentiment="neutral",
        score=6.0,
    )
    assert ctx.sentiment == "neutral"
    assert ctx.score == 6.0


def test_news_signal_defaults():
    sig = NewsSignal(theme="test")
    assert sig.sentiment == ""
    assert sig.catalyst_strength == 0.0
    assert sig.related_sectors == []


def test_sector_momentum_signal_defaults():
    sig = SectorMomentumSignal(board_code="BK001", name="test")
    assert sig.trend == ""
    assert sig.rank_change == 0


def test_market_breadth_context_defaults():
    ctx = MarketBreadthContext()
    assert ctx.sentiment == ""
    assert ctx.score == 0.0
