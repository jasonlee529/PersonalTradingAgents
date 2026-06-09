import pytest

from src.agents.sector_discovery.aggregator import SectorAggregator
from src.agents.sector_discovery.models import StockSignal


@pytest.fixture
def aggregator():
    return SectorAggregator()


def test_aggregator_handles_news_dimension(aggregator):
    signals = [
        StockSignal(symbol="000001", name="平安银行", score=7.0, dimension="news", reason="光刻机突破"),
    ]
    result = aggregator.aggregate(signals)
    assert len(result) == 1
    assert result[0].news_score > 0


def test_aggregator_handles_correction_dimension(aggregator):
    signals = [
        StockSignal(symbol="000001", name="平安银行", score=6.0, dimension="correction", reason="回调低吸"),
    ]
    result = aggregator.aggregate(signals)
    assert len(result) == 1
    assert result[0].correction_score > 0


def test_aggregator_composite_includes_new_dimensions(aggregator):
    signals = [
        StockSignal(symbol="000001", name="平安银行", score=8.0, dimension="market_heat", reason="涨停"),
        StockSignal(symbol="000001", name="平安银行", score=7.0, dimension="news", reason="光刻机突破"),
        StockSignal(symbol="000001", name="平安银行", score=6.0, dimension="correction", reason="回调"),
    ]
    result = aggregator.aggregate(signals)
    assert len(result) == 1
    # Should have market_heat + news + correction averaged, with dim boost
    assert result[0].composite_score > 5.0

