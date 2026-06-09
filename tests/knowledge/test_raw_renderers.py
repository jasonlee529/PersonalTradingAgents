from src.knowledge.raw_renderers import (
    render_announcement,
    render_daily_trade_log,
    render_news_article,
    render_research_report,
)


def test_render_daily_trade_log_includes_audit_sections():
    markdown = render_daily_trade_log(
        "2026-06-04",
        [
            {
                "symbol": "603738",
                "action": "buy",
                "quantity": 1000,
                "price": 12.3,
                "commission": 5,
                "tax": 0,
                "other_fees": 0,
                "reason": "测试",
            }
        ],
        audit={
            "before_positions": {"603738": {"quantity": 0, "avg_cost": 0}},
            "system_positions": {"603738": {"quantity": 1000, "avg_cost": 12.305}},
            "final_positions": {"603738": {"quantity": 1000, "avg_cost": 12.305}},
            "overrides": [],
        },
    )
    assert "# 2026-06-04 每日操作记录" in markdown
    assert "## 持仓更新" in markdown
    assert "603738" in markdown


def test_external_renderers_fallback_body():
    news = render_news_article("603738", {"title": "新闻", "url": "https://example.com"})
    assert "当前接口仅返回链接/摘要" in news

    ann = render_announcement("603738", {"title": "公告"})
    assert "完整公告正文" in ann

    report = render_research_report("603738", {"title": "研报"})
    assert "完整研报正文" in report
