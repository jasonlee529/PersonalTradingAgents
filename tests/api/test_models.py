from src.api.models import (
    HoldingCreate, HoldingResponse, PositionResponse, HoldingDetailResponse,
    QuoteResponse, KlineRecord, KlineResponse, FundamentalsResponse,
    IndicatorResponse, NewsItem, AnnouncementItem, ResearchReportItem,
    StockSnapshotResponse, AnalysisRequest, AnalysisStatusResponse,
    SettingsResponse, SettingsUpdate,
)


def test_models_importable():
    assert HoldingCreate(symbol="TEST")
    assert QuoteResponse(symbol="TEST", price=1.0, open=1.0, high=1.0, low=1.0, prev_close=1.0, volume=1, turnover=1.0, change_pct=0.0)
    assert KlineRecord(date="2024-01-01", open=1, high=1, low=1, close=1, volume=1, turnover=1, change_pct=0)
    assert FundamentalsResponse(symbol="TEST", pe_ttm=10, pb=1, roe=10, revenue_growth=5, profit_growth=5, debt_ratio=30)
    assert AnalysisStatusResponse(job_id="1", symbol="TEST", status="pending", progress="")
    assert SettingsResponse(
        daily_direction_llm_provider="", wiki_llm_provider="",
        llm_provider_configs={},
        openai_api_key="", deepseek_api_key="", anthropic_api_key="", google_api_key="",
        azure_openai_api_key="", xai_api_key="", dashscope_api_key="", dashscope_cn_api_key="",
        zhipu_api_key="", zhipu_cn_api_key="", minimax_api_key="", minimax_cn_api_key="", openrouter_api_key="", kimi_api_key="",
        scheduler_enabled=False, analysis_schedule="0 9 * * 1-5",
        daily_direction_notification_enabled=False,
        notification_report_channels="", wechat_webhook_url="", wechat_msg_type="markdown", wechat_max_bytes=4000,
        feishu_webhook_url="", feishu_webhook_secret="", feishu_webhook_keyword="", feishu_max_bytes=20000,
        email_sender="", email_password="", email_receivers="", email_sender_name="TradingAgents",
        webhook_verify_ssl=True,
        test_mode=False,
        trade_commission_rate=0.00025,
        trade_min_commission=5.0,
        trade_stamp_tax_rate=0.0005,
        trade_transfer_fee_rate=0.00001,
        xueqiu_cookie="",
        xueqiu_auto_cookie=True,
        xueqiu_timeout=10.0,
    )
    assert SettingsUpdate(xueqiu_cookie=None, xueqiu_auto_cookie=None, xueqiu_timeout=None)
