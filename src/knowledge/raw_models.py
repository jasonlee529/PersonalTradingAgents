from typing import Literal

from pydantic import BaseModel, Field


RAW_SOURCE_KINDS = {
    "daily_direction",
    "analysis_memory",
    "stock_analysis",
    "news_article",
    "announcement",
    "research_report",
    "manual_source",
    "daily_trade_log",
    "portfolio_snapshot",
}

RAW_SOURCE_KIND_LABELS = {
    "daily_direction": "今日方向",
    "analysis_memory": "分析记忆",
    "stock_analysis": "个股分析",
    "news_article": "新闻",
    "announcement": "公告",
    "research_report": "研报",
    "manual_source": "手动材料",
    "daily_trade_log": "每日操作",
    "portfolio_snapshot": "持仓快照",
}

RAW_ORIGINS = {"agent", "external", "user", "system"}

TRADE_ACTIONS = {"buy", "sell", "add", "reduce", "clear", "hold", "watch"}


def label_for_source_kind(source_kind: str) -> str:
    return RAW_SOURCE_KIND_LABELS.get(source_kind, source_kind or "-")


class RawSourceCreateRequest(BaseModel):
    source_kind: str
    origin: str
    title: str
    markdown: str
    metadata: dict = Field(default_factory=dict)


class RawMetadataUpdateRequest(BaseModel):
    tags: list[str] | None = None
    metadata: dict | None = None


class RawSourceUpdateRequest(BaseModel):
    title: str
    markdown: str
    metadata: dict | None = None


class DailyTradeLogEntry(BaseModel):
    symbol: str
    name: str = ""
    action: Literal["buy", "sell", "add", "reduce", "clear", "hold", "watch"]
    quantity: int | None = None
    price: float | None = None
    commission: float = 0.0
    tax: float = 0.0
    other_fees: float = 0.0
    reason: str = ""
    linked_analysis_run_id: str = ""
    linked_source_ids: list[str] = Field(default_factory=list)


class PositionOverride(BaseModel):
    symbol: str
    final_quantity: int
    final_avg_cost: float
    final_current_price: float | None = None
    override_reason: str = ""


class DailyTradeLogRequest(BaseModel):
    trade_date: str
    entries: list[DailyTradeLogEntry]
    position_overrides: list[PositionOverride] = Field(default_factory=list)
    notes: str = ""
