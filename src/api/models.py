from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from src.portfolio.models import Market, DataStatus


# --- Portfolio ---

class HoldingCreate(BaseModel):
    symbol: str
    name: str = ""
    market: Market = Market.CN
    quantity: int = 0
    avg_cost: float = 0.0


class HoldingResponse(BaseModel):
    symbol: str
    name: str
    market: str
    tags: list[str]
    data_status: str
    created_at: datetime


class PositionResponse(BaseModel):
    symbol: str
    quantity: int
    avg_cost: float
    current_price: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    updated_at: datetime


class HoldingDetailResponse(BaseModel):
    holding: HoldingResponse
    position: Optional[PositionResponse] = None


class TradeRecordResponse(BaseModel):
    id: int
    symbol: str
    action: str
    quantity: int
    price: float
    old_quantity: int
    new_quantity: int
    reason: str
    commission: float
    tax: float
    other_fees: float
    amount: float
    raw_source_id: str
    recorded_at: datetime


# --- Stock Data ---

class QuoteResponse(BaseModel):
    name: str = ""
    symbol: str
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: int
    turnover: float
    change_pct: float


class LimitUpStockItem(BaseModel):
    symbol: str
    name: str = ""
    market: str = ""
    trade_date: str
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[int] = None
    turnover: Optional[float] = None
    turnover_rate: Optional[float] = None
    first_limit_up_time: Optional[str] = None
    last_limit_up_time: Optional[str] = None
    seal_amount: Optional[float] = None
    consecutive_days: Optional[int] = None
    reason: str = ""
    source: str = ""


class LimitUpStockListResponse(BaseModel):
    trade_date: str
    market: str
    total: int
    limit: int
    offset: int
    items: list[LimitUpStockItem]
    error: str = ""


class KlineRecord(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float
    change_pct: float


class KlineResponse(BaseModel):
    symbol: str
    period: str
    data: list[KlineRecord]


class FundamentalsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    name: str = ""
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth: Optional[float] = None
    profit_growth: Optional[float] = None
    debt_ratio: Optional[float] = None


class IndicatorResponse(BaseModel):
    symbol: str
    indicators: dict


class NewsItem(BaseModel):
    title: str
    content: str = ""
    source: str = ""
    published_at: str = ""
    url: str = ""
    relevance_score: float = 0.0


class AnnouncementItem(BaseModel):
    title: str
    type: str = ""
    published_at: str = ""
    url: str = ""


class ResearchReportItem(BaseModel):
    title: str
    institution: str = ""
    rating: str = ""
    target_price: str = ""
    published_at: str = ""
    url: str = ""
    predict_this_year_eps: Optional[str] = None
    predict_next_year_eps: Optional[str] = None


class StockSnapshotResponse(BaseModel):
    symbol: str
    quote: Optional[QuoteResponse] = None
    kline: list[KlineRecord] = Field(default_factory=list)
    fundamentals: Optional[FundamentalsResponse] = None
    indicators: Optional[IndicatorResponse] = None
    news: list[NewsItem] = Field(default_factory=list)
    announcements: list[AnnouncementItem] = Field(default_factory=list)
    research_reports: list[ResearchReportItem] = Field(default_factory=list)


# --- Position ---

class PositionInput(BaseModel):
    """User's current holding state for a symbol."""
    quantity: int = 0
    avg_cost: float = 0.0
    hold_days: int = 0


class PositionUpdate(BaseModel):
    """Direct position update by user."""
    quantity: int
    avg_cost: float
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    override_reason: str = ""


# --- Analysis ---

class AnalysisStepItem(BaseModel):
    step_id: str
    label: str
    role: str
    character: str
    module: str = ""
    action: str = ""
    artifact_key: str = ""
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    detail: str = ""


class AnalysisRequest(BaseModel):
    symbol: str
    output_language: Optional[str] = None  # override config, e.g. "Chinese"
    analysts: Optional[list[str]] = None   # e.g. ["market", "sentiment", "news", "fundamentals"]
    research_depth: Optional[str] = None   # "deep" or "quick"
    llm_provider: Optional[str] = None
    thinking_agents: Optional[bool] = None
    trade_date: Optional[str] = None       # YYYY-MM-DD, defaults to today
    checkpoint_enabled: Optional[bool] = None  # per-job checkpoint override
    position: Optional[PositionInput] = None


class AnalysisJobListItem(BaseModel):
    job_id: str
    symbol: str
    status: str
    progress: str
    created_at: Optional[str] = None


class AnalysisStatusResponse(BaseModel):
    job_id: str
    symbol: str
    status: str
    phase: str = ""
    progress: str = ""
    result_summary: str = ""
    error: str = ""
    steps: list[AnalysisStepItem] = Field(default_factory=list)
    created_at: Optional[str] = None
    output_files: list[str] = Field(default_factory=list)


class AnalysisFeedbackRequest(BaseModel):
    step_id: str
    feedback_type: str  # "upvote" | "downvote"
    comment: str = ""


class AnalysisFeedbackItem(BaseModel):
    step_id: str
    feedback_type: str
    comment: str
    created_at: str


class AnalysisFeedbackResponse(BaseModel):
    job_id: str
    feedbacks: list[AnalysisFeedbackItem]
    summary: dict


# --- Sector Discovery ---

class DiscoverPhaseItem(BaseModel):
    phase: str
    label: str
    status: str  # pending | running | success | failure | timeout | fallback
    duration_ms: int = 0
    message: str = ""


class DiscoverStatusResponse(BaseModel):
    job_id: str
    status: str  # pending | running | completed | failed
    progress_pct: int = 0
    phase: str = ""
    message: str = ""
    error: str = ""
    phases: list[DiscoverPhaseItem] = Field(default_factory=list)
    result_summary: str = ""
    created_at: str = ""
    completed_at: Optional[str] = None


# --- Settings ---

class LLMProviderSettings(BaseModel):
    quick_model: str = ""
    deep_model: str = ""
    api_key: str = ""


class LLMProviderSettingsUpdate(BaseModel):
    quick_model: Optional[str] = None
    deep_model: Optional[str] = None
    api_key: Optional[str] = None


class SettingsResponse(BaseModel):
    # LLM
    daily_direction_llm_provider: str = ""
    wiki_llm_provider: str = ""
    llm_provider_configs: dict[str, "LLMProviderSettings"] = Field(default_factory=dict)
    # API Keys
    openai_api_key: str
    deepseek_api_key: str
    anthropic_api_key: str
    google_api_key: str
    azure_openai_api_key: str
    xai_api_key: str
    dashscope_api_key: str
    dashscope_cn_api_key: str
    zhipu_api_key: str
    zhipu_cn_api_key: str
    minimax_api_key: str
    minimax_cn_api_key: str
    openrouter_api_key: str
    kimi_api_key: str
    # Scheduler
    scheduler_enabled: bool
    analysis_schedule: str
    daily_direction_notification_enabled: bool
    notification_report_channels: str
    wechat_webhook_url: str
    wechat_msg_type: str
    wechat_max_bytes: int
    feishu_webhook_url: str
    feishu_webhook_secret: str
    feishu_webhook_keyword: str
    feishu_max_bytes: int
    email_sender: str
    email_password: str
    email_receivers: str
    email_sender_name: str
    webhook_verify_ssl: bool
    test_mode: bool
    trade_commission_rate: float
    trade_min_commission: float
    trade_stamp_tax_rate: float
    trade_transfer_fee_rate: float
    xueqiu_cookie: str = ""
    xueqiu_auto_cookie: bool = True
    xueqiu_timeout: float = 10.0
    tushare_api_key: str = ""
    fund_holdings_refresh_enabled: bool = False
    fund_holdings_refresh_schedule: str = "0 2 * * 1-5"


class AnalystInfo(BaseModel):
    name: str
    label: str
    report_key: str
    llm_type: str


class AnalystsResponse(BaseModel):
    analysts: list[AnalystInfo]
    defaults: list[str]


class LLMProviderInfo(BaseModel):
    id: str
    label: str
    region: str
    api_key_field: str
    api_key_env: Optional[str] = None
    default_base_url: str
    default_quick_model: str
    default_deep_model: str
    requires_api_key: bool
    supports_custom_model: bool


class LLMProvidersResponse(BaseModel):
    providers: list[LLMProviderInfo]


# --- Scheduler tasks ---

class ScheduledTaskResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    cron: str


class ScheduledTaskUpdate(BaseModel):
    enabled: Optional[bool] = None
    cron: Optional[str] = None


class RunTaskResponse(BaseModel):
    task_id: str
    success: bool
    message: str


class SettingsUpdate(BaseModel):
    # LLM
    daily_direction_llm_provider: Optional[str] = None
    wiki_llm_provider: Optional[str] = None
    llm_provider_configs: Optional[dict[str, LLMProviderSettingsUpdate]] = None
    # API Keys
    openai_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    xai_api_key: Optional[str] = None
    dashscope_api_key: Optional[str] = None
    dashscope_cn_api_key: Optional[str] = None
    zhipu_api_key: Optional[str] = None
    zhipu_cn_api_key: Optional[str] = None
    minimax_api_key: Optional[str] = None
    minimax_cn_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    kimi_api_key: Optional[str] = None
    # Scheduler
    scheduler_enabled: Optional[bool] = None
    analysis_schedule: Optional[str] = None
    daily_direction_notification_enabled: Optional[bool] = None
    notification_report_channels: Optional[str] = None
    wechat_webhook_url: Optional[str] = None
    wechat_msg_type: Optional[str] = None
    wechat_max_bytes: Optional[int] = None
    feishu_webhook_url: Optional[str] = None
    feishu_webhook_secret: Optional[str] = None
    feishu_webhook_keyword: Optional[str] = None
    feishu_max_bytes: Optional[int] = None
    email_sender: Optional[str] = None
    email_password: Optional[str] = None
    email_receivers: Optional[str] = None
    email_sender_name: Optional[str] = None
    webhook_verify_ssl: Optional[bool] = None
    test_mode: Optional[bool] = None
    trade_commission_rate: Optional[float] = None
    trade_min_commission: Optional[float] = None
    trade_stamp_tax_rate: Optional[float] = None
    trade_transfer_fee_rate: Optional[float] = None
    xueqiu_cookie: Optional[str] = None
    xueqiu_auto_cookie: Optional[bool] = None
    xueqiu_timeout: Optional[float] = None
    tushare_api_key: Optional[str] = None
    fund_holdings_refresh_enabled: Optional[bool] = None
    fund_holdings_refresh_schedule: Optional[str] = None
