import pytest

from src.knowledge.wiki_renderers import (
    render_frontmatter,
    render_stock_profile_template,
    render_stock_timeline_template,
    render_stock_analysis_runs_template,
    render_topic_template,
    render_daily_direction_template,
    render_trade_month_template,
    render_portfolio_overview_template,
    render_claims_page_template,
    render_source_digest_page,
    render_analysis_run_digest_page,
    render_index_page,
    render_log_entry,
)


def test_render_frontmatter():
    fm = render_frontmatter({"page_id": "test", "title": "T"})
    assert fm.startswith("---\n")
    assert "page_id: test" in fm
    assert fm.endswith("\n\n")


def test_render_stock_profile_template():
    md = render_stock_profile_template("603738", "603738 泰晶科技")
    assert "# 603738 泰晶科技" in md
    assert "wiki-section:start:summary" in md
    assert "wiki-section:start:position" in md
    assert "wiki-section:start:thesis" in md
    assert "wiki-section:start:catalysts" in md
    assert "wiki-section:start:risks" in md
    assert "wiki-section:start:evidence" in md
    assert "wiki-section:start:recent_updates" in md
    assert "wiki-section:start:links" in md


def test_render_stock_timeline_template():
    md = render_stock_timeline_template("603738")
    assert "# 603738 时间线" in md


def test_render_stock_analysis_runs_template():
    md = render_stock_analysis_runs_template("603738")
    assert "# 603738 分析 Run 列表" in md
    assert "| 日期时间 |" in md


def test_render_topic_template():
    md = render_topic_template("半导体", "semiconductor")
    assert "# 半导体" in md
    assert "wiki-section:start:definition" in md
    assert "wiki-section:start:current_view" in md
    assert "wiki-section:start:related_stocks" in md
    assert "wiki-section:start:catalysts" in md
    assert "wiki-section:start:risks" in md
    assert "wiki-section:start:evidence" in md


def test_render_daily_direction_template():
    md = render_daily_direction_template("2026-06-05")
    assert "# 2026-06-05 今日方向" in md
    assert "wiki-section:start:latest" in md
    assert "wiki-section:start:runs" in md
    assert "wiki-section:start:portfolio_relation" in md
    assert "wiki-section:start:validation" in md


def test_render_trade_month_template():
    md = render_trade_month_template("2026-06")
    assert "# 2026-06 交易记录" in md
    assert "wiki-section:start:summary" in md
    assert "wiki-section:start:entries" in md
    assert "wiki-section:start:ai_vs_actual" in md
    assert "wiki-section:start:review" in md


def test_render_portfolio_overview_template():
    md = render_portfolio_overview_template()
    assert "# 组合总览" in md
    assert "wiki-section:start:structure" in md


def test_render_claims_page_template():
    md1 = render_claims_page_template("contradictions")
    assert "# 观点冲突" in md1
    md2 = render_claims_page_template("open_questions")
    assert "# 待验证问题" in md2


def test_render_source_digest_page():
    source = {
        "source_id": "news_article:abc",
        "source_kind": "news_article",
        "title": "测试新闻",
        "provider": "eastmoney",
        "published_at": "2026-06-05",
        "content_sha256": "sha256",
    }
    claims = [{"claim_id": "claim:1", "statement": "需求上升"}]
    md = render_source_digest_page(source, "摘要内容", claims)
    assert "# 测试新闻" in md
    assert "news_article:abc" in md
    assert "sha256" in md
    assert "需求上升" in md


def test_render_analysis_run_digest_page():
    sources = [
        {"title": "市场分析", "metadata": {"analysis_node": "market_report"}, "symbol": "603738", "trade_date": "2026-06-05"},
    ]
    claims = [{"claim_id": "claim:1", "statement": "建议持有"}]
    md = render_analysis_run_digest_page(sources, "综合结论", claims)
    assert "603738 2026-06-05 分析 Run" in md
    assert "综合结论" in md
    assert "market_report" in md
    assert "建议持有" in md


def test_render_index_page():
    pages = [
        {"page_type": "stock_profile", "slug": "stocks/603738", "title": "603738", "updated_at": "2026-06-05"},
        {"page_type": "topic", "slug": "topics/ai", "title": "AI", "updated_at": "2026-06-04"},
    ]
    md = render_index_page(pages, [], [])
    assert "# PersonalTradingAgents Wiki" in md
    assert "603738" in md
    assert "AI" in md


def test_render_log_entry():
    run = {
        "run_id": "r1",
        "started_at": "2026-06-05T14:30:00",
        "trigger_type": "source",
        "source_id": "manual_source:abc",
        "status": "completed",
        "pages_touched": [{"slug": "stocks/603738", "title": "603738"}],
        "claims_touched": ["claim:1"],
    }
    md = render_log_entry(run)
    assert "source" in md
    assert "manual_source:abc" in md
    assert "completed" in md
