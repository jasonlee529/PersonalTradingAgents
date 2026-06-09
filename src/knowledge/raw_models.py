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
}

RAW_ORIGINS = {"agent", "external", "user", "system"}

TRADE_ACTIONS = {"buy", "sell", "add", "reduce", "clear", "hold", "watch"}


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
