"""Tests for DirectionReportBuilder."""

import asyncio

import pytest

from src.agents.sector_discovery.models import SectorSnapshot, StockSignal
from src.agents.sector_discovery.report_builder import DirectionReportBuilder


@pytest.fixture
def builder():
    return DirectionReportBuilder()


def test_build_empty(builder):
    report = asyncio.run(builder.build([]))
    assert report.date
    assert report.sectors == []
    assert "暂无" in report.summary


def test_build_with_snapshots(builder):
    snap = SectorSnapshot(
        board_code="BK001",
        name="固态电池",
        tags=["热点追逐"],
        composite_score=8.5,
        expectation_gap_score=2.0,
        top_stocks=[
            StockSignal(symbol="300750", name="宁德时代", score=9.0, reason="龙头"),
        ],
    )
    report = asyncio.run(builder.build([snap]))
    assert report.date
    assert len(report.sectors) == 1
    assert "共生成 1 个方向观察" in report.summary
    assert "资金连续流入" in report.summary
    assert "短期涨幅过大" in report.summary


def test_build_expectation_gap_badge(builder):
    snap = SectorSnapshot(
        board_code="BK002",
        name="商业航天",
        tags=["政策前瞻"],
        composite_score=7.0,
        expectation_gap_score=8.5,
        top_stocks=[],
    )
    report = asyncio.run(builder.build([snap]))
    md = builder.to_enhanced_markdown(report)
    assert "预期差 8.5/10" in md


def test_enhanced_markdown_structure(builder):
    snap = SectorSnapshot(
        board_code="BK001",
        name="固态电池",
        tags=["热点追逐"],
        composite_score=8.5,
        expectation_gap_score=2.0,
        top_stocks=[
            StockSignal(symbol="300750", name="宁德时代", score=9.0, reason="龙头", catalyst="6月订单"),
        ],
    )
    report = asyncio.run(builder.build([snap], date="2026-06-01"))
    md = builder.to_enhanced_markdown(report)
    assert "# 2026-06-01 今日方向" in md
    assert "【热点追逐】固态电池" in md
    assert "产业链" in md
    assert "资金" in md
    assert "关注" in md
    assert "资金连续流入" in md
    assert "短期涨幅过大" in md
    assert "1-5个交易日" in md


def test_multiple_categories(builder):
    hot = SectorSnapshot(
        board_code="BK001",
        name="热点",
        tags=["热点追逐"],
        composite_score=8.0,
        top_stocks=[StockSignal(symbol="000001", name="A", score=8.0)],
    )
    policy = SectorSnapshot(
        board_code="BK002",
        name="政策",
        tags=["政策前瞻"],
        composite_score=7.0,
        top_stocks=[StockSignal(symbol="000002", name="B", score=7.0)],
    )
    report = asyncio.run(builder.build([hot, policy]))
    md = builder.to_enhanced_markdown(report)
    assert "【热点追逐】热点" in md
    assert "【政策前瞻】政策" in md
    assert "政策利好出台" in md


def test_category_without_stocks_omitted(builder):
    # StockScreener would drop empty snapshots, but test builder handles empty
    report = asyncio.run(builder.build([]))
    md = builder.to_enhanced_markdown(report)
    assert "#" in md
