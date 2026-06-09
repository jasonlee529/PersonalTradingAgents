import pytest
from src.news.relevance import compute_relevance


def test_exact_match_high_score():
    score = compute_relevance(
        title="600519贵州茅台发布年报",
        content="600519贵州茅台2025年营收增长15%",
        symbol="600519",
        name="贵州茅台",
    )
    assert score >= 0.8


def test_no_match_low_score():
    score = compute_relevance(
        title="比亚迪新能源销量创新高",
        content="比亚迪",
        symbol="600519",
        name="贵州茅台",
    )
    assert score < 0.3


def test_symbol_match_only():
    score = compute_relevance(
        title="600519盘中异动",
        content="市场观察",
        symbol="600519",
        name="",
    )
    assert score == 0.5
