"""Data models for Sector Discovery scan results and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


@dataclass
class StockSignal:
    """A single stock signal from any scanner dimension."""
    symbol: str
    name: str
    score: float = 0.0  # 0-10
    dimension: str = ""  # market_heat / policy / fund / value / chain
    reason: str = ""
    catalyst: str = ""  # e.g. "6月招标季"
    time_horizon: str = ""  # short / medium / long
    metadata: dict = field(default_factory=dict)  # raw metrics for ranker/screener


@dataclass
class SectorSnapshot:
    """Aggregated view of a sector/concept board."""
    board_code: str
    name: str
    change_pct: float = 0.0
    # Five-dimension scores (0-10 each)
    market_heat_score: float = 0.0
    policy_score: float = 0.0
    fund_score: float = 0.0
    value_score: float = 0.0
    chain_score: float = 0.0
    news_score: float = 0.0
    correction_score: float = 0.0
    momentum_score: float = 0.0
    # Composite + expectation-gap score
    composite_score: float = 0.0
    expectation_gap_score: float = 0.0
    # Classification
    tags: list[str] = field(default_factory=list)  # e.g. ["热点追逐", "固态电池"]
    # Top stocks in this sector
    top_stocks: list[StockSignal] = field(default_factory=list)
    # Raw metrics aggregated from scanner signals (for ranker/screener use)
    raw_metrics: dict = field(default_factory=dict)


# ── Agent I/O Models ──────────────────────────────────────────────────────


@dataclass
class SignalEvidence:
    """A single piece of evidence supporting a candidate direction."""
    source: str                        # market_heat / policy / fund / value / chain / news
    description: str                   # signal description
    strength: float                    # 0-10
    data_snapshot: dict = field(default_factory=dict)


@dataclass
class CandidateDirection:
    """A candidate direction discovered by Scout Agent."""
    name: str
    category: str                      # 热点追逐/政策前瞻/机构错配/价值蓄势/产业链预期差
    confidence: float                  # 0-10
    evidence_signals: list[SignalEvidence] = field(default_factory=list)
    raw_metrics: dict = field(default_factory=dict)


@dataclass
class DimensionValidation:
    """Validation result for a single dimension."""
    dimension: str                     # fund / policy / sentiment
    status: Literal["strong", "moderate", "weak", "missing"]
    score: float                       # 0-10
    evidence: str = ""
    concerns: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Full validation report for a candidate direction."""
    direction_name: str
    overall_status: Literal["PASS", "FLAG", "REJECT"]
    fund_validation: DimensionValidation = field(default_factory=lambda: DimensionValidation(dimension="fund", status="missing", score=0.0))
    policy_validation: DimensionValidation = field(default_factory=lambda: DimensionValidation(dimension="policy", status="missing", score=0.0))
    sentiment_validation: DimensionValidation = field(default_factory=lambda: DimensionValidation(dimension="sentiment", status="missing", score=0.0))
    score_after_validation: float = 0.0
    rejection_reason: str = ""
    watch_points: list[str] = field(default_factory=list)


@dataclass
class SelectedDirection:
    """A direction selected by Comparator Agent."""
    name: str
    rank: int
    total_score: float
    fund_score: float = 0.0
    policy_score: float = 0.0
    sentiment_score: float = 0.0
    chain_depth_score: float = 0.0
    catalyst_score: float = 0.0
    selection_reason: str = ""
    comparison_notes: str = ""
    eliminated_peers: list[str] = field(default_factory=list)


@dataclass
class ChainSegmentAnalysis:
    """Analysis of a single supply chain segment."""
    segment_name: str
    position: Literal["upstream", "midstream", "downstream", "supporting"]
    market_perception: str = ""
    reality_assessment: str = ""
    expectation_gap: float = 0.0
    key_players: list[str] = field(default_factory=list)
    price_trend: str = ""
    capacity_utilization: str = ""
    order_backlog_trend: str = ""
    investment_logic: str = ""
    time_horizon: str = ""


@dataclass
class ChainAnalysisReport:
    """Full supply chain analysis for a direction."""
    direction_name: str
    segments: list[ChainSegmentAnalysis] = field(default_factory=list)
    top_segment: str = ""
    diffusion_path: str = ""
    supporting_segments: list[str] = field(default_factory=list)


@dataclass
class CatalystEvent:
    """A single catalyst event."""
    event_name: str
    expected_date: str | None = None
    time_category: Literal["past", "imminent", "expected", "long_term"] = "expected"
    market_priced_in: float = 0.0
    impact_assessment: str = ""
    data_to_watch: str = ""


@dataclass
class CatalystTimeline:
    """Timeline of catalyst events for a direction."""
    direction_name: str
    events: list[CatalystEvent] = field(default_factory=list)
    next_key_event: str = ""
    recommended_action: str = ""


@dataclass
class RiskTrigger:
    """A single risk trigger condition."""
    condition: str
    metric_name: str = ""
    threshold: str = ""
    severity: Literal["warning", "critical"] = "warning"


@dataclass
class RiskAssessment:
    """Full risk assessment for a direction."""
    direction_name: str
    overall_risk_level: Literal["low", "moderate", "high"] = "moderate"
    market_risks: list[RiskTrigger] = field(default_factory=list)
    policy_risks: list[RiskTrigger] = field(default_factory=list)
    fundamental_risks: list[RiskTrigger] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    alternative_directions: list[str] = field(default_factory=list)


@dataclass
class DeepAnalysis:
    """Aggregated deep analysis for a single direction."""
    chain: ChainAnalysisReport | None = None
    catalyst: CatalystTimeline | None = None
    risk: RiskAssessment | None = None


@dataclass
class AgentExecutionRecord:
    """Log entry for agent execution."""
    agent_name: str
    phase: str
    status: Literal["success", "failure", "timeout", "fallback"]
    duration_ms: int = 0
    message: str = ""


@dataclass
class DirectionContext:
    """Shared state object across all analysis phases."""
    date: str
    original_date: str = ""  # The date before normalization (for non-trading-day detection)
    market_overview: dict | None = None
    news_context: str = ""
    candidate_directions: list[CandidateDirection] = field(default_factory=list)
    validation_results: list[ValidationReport] = field(default_factory=list)
    selected_directions: list[SelectedDirection] = field(default_factory=list)
    deep_analysis: dict[str, DeepAnalysis] = field(default_factory=dict)
    execution_log: list[AgentExecutionRecord] = field(default_factory=list)

    @property
    def is_non_trading_day(self) -> bool:
        """True if the original date was adjusted because it fell on a non-trading day."""
        return bool(self.original_date) and self.original_date != self.date


@dataclass
class DirectionReport:
    """Final daily direction recommendation report."""
    date: str
    sectors: list[SectorSnapshot] = field(default_factory=list)
    summary: str = ""

    def to_markdown(self) -> str:
        """Render report as markdown."""
        summary = (self.summary or "").strip()
        first_line = summary.splitlines()[0] if summary else ""
        if first_line.startswith("# ") and "今日方向" in first_line:
            return summary
        if not summary:
            summary = "暂无有效方向信号。"
        return f"# {self.date} 今日方向\n\n{summary}"


@dataclass
class NewsSignal:
    """A news-derived signal with theme, sentiment, and catalyst assessment."""
    theme: str
    sentiment: Literal["positive", "negative", "neutral"] = ""
    related_sectors: list[str] = field(default_factory=list)
    catalyst_strength: float = 0.0  # 0-10
    time_window: Literal["immediate", "short", "medium"] = ""
    source_headline: str = ""
    reasoning: str = ""


@dataclass
class SectorMomentumSignal:
    """Industry/concept board momentum trend signal."""
    board_code: str
    name: str
    rank_change: int = 0  # vs last week
    trend: Literal["rising", "falling", "stable", "sudden_up", "sudden_down"] = ""
    composite_score: float = 0.0  # 0-10


@dataclass
class MarketBreadthContext:
    """Overall market breadth and sentiment context."""
    advance_decline_ratio: float = 0.0
    limit_up_count: int = 0
    limit_down_count: int = 0
    sentiment: Literal["overheated", "neutral", "panic"] = ""
    score: float = 0.0  # 0-10 (higher = more bullish)


# ── Signal source models (Phase 0-1) ──────────────────────────────────────


@dataclass
class HotSignal:
    """A hot concept detected by MarketHeatScanner — used as input to ChainMapper."""

    concept: str  # e.g. "固态电池"
    heat_level: float = 0.0  # 0-10
    evidence: str = ""  # e.g. "5股涨停，资金连续3日流入30亿"
    market_heatmap: list[str] = field(default_factory=list)  # limit-up stock codes
    order_flow_profile: float = 0.0  # total net fund flow (yuan)


@dataclass
class ChainSignal:
    """Output from ChainMapper — upstream segments with expectation-gap scores."""

    concept: str  # e.g. "固态电池"
    segment_name: str  # e.g. "铝塑膜"
    position: str = ""  # upstream / midstream / downstream
    expectation_gap_score: float = 0.0  # 0-10
    reasoning: str = ""  # why this segment has expectation gap
    board_keywords: list[str] = field(default_factory=list)  # for matching concept boards


# ── LLM structured-output schemas ─────────────────────────────────────────


class ChainSegment(BaseModel):
    """A single supply-chain segment produced by LLM reasoning."""

    name: str = Field(description="Segment name, e.g. 铝塑膜, 航天锻件")
    position: Literal["upstream", "midstream", "downstream"] = Field(
        description="Supply-chain position"
    )
    expectation_gap_score: float = Field(
        ge=0, le=10, description="Expectation-gap score 0-10. Higher = larger gap."
    )
    reasoning: str = Field(description="Why this segment has expectation gap")
    board_keywords: list[str] = Field(
        description="A-share concept-board keywords for matching, e.g. ['铝塑膜', '电池材料']"
    )


class ChainAnalysis(BaseModel):
    """Full LLM output for supply-chain reasoning."""

    concept: str = Field(description="The original hot concept")
    segments: list[ChainSegment] = Field(description="All identified segments")
    top_segments: list[str] = Field(
        default_factory=list,
        description="Names of top 2-3 segments with highest expectation gap",
    )


