"""NewsAnalyst — LLM-driven news theme extraction and sector mapping.

Analyzes global news and announcements to extract:
- Core theme
- Sentiment (positive/negative/neutral)
- Related A-share concept sectors
- Catalyst strength (0-10)
- Time window (immediate/short/medium)
- Reasoning

Output: NewsSignal[] for pipeline aggregation.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from src.agents.sector_discovery.llm_utils import (
    SectorDiscoveryLLMError,
    llm_structured_output,
)
from src.agents.sector_discovery.models import NewsSignal
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


class NewsSignalSchema(BaseModel):
    """Single news-derived signal."""
    theme: str = Field(description="核心主题，如'半导体设备国产替代'")
    sentiment: str = Field(description="情感倾向: positive / negative / neutral")
    related_sectors: list[str] = Field(description="最相关的A股概念板块，2-3个")
    catalyst_strength: float = Field(ge=0, le=10, description="催化强度 0-10")
    time_window: str = Field(description="时间窗口: immediate / short / medium")
    source_headline: str = Field(description="来源新闻标题")
    reasoning: str = Field(description="为什么这个主题重要")

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "theme" not in data and "core_theme" in data:
            data["theme"] = data["core_theme"]
        if "catalyst_strength" not in data and "catalyst_intensity" in data:
            data["catalyst_strength"] = data["catalyst_intensity"]
        if "time_window" not in data and "time_horizon" in data:
            data["time_window"] = data["time_horizon"]
        if "source_headline" not in data:
            data["source_headline"] = data.get("headline") or data.get("theme") or ""
        return data


class NewsAnalysis(BaseModel):
    """LLM output for batch news analysis."""
    signals: list[NewsSignalSchema] = Field(description="提取的所有新闻信号")

    @model_validator(mode="before")
    @classmethod
    def _coerce_single_signal(cls, value: Any) -> Any:
        if isinstance(value, list):
            return {"signals": value}
        if not isinstance(value, dict) or "signals" in value:
            return value
        signal_keys = {"theme", "core_theme", "related_sectors", "catalyst_strength", "catalyst_intensity"}
        if signal_keys.intersection(value):
            return {"signals": [value]}
        return value


_NEWS_ANALYSIS_PROMPT = """请分析以下新闻，提取投资主题信号。
Output must be valid JSON matching this exact schema. Do not include markdown or extra text.

Required JSON object shape:
{{
  "signals": [
    {{
      "theme": "short investment theme",
      "sentiment": "positive|negative|neutral",
      "related_sectors": ["sector1", "sector2"],
      "catalyst_strength": 0,
      "time_window": "immediate|short|medium",
      "source_headline": "source headline",
      "reasoning": "why it matters"
    }}
  ]
}}

Do not output a single top-level theme object. Always wrap extracted themes in the "signals" array.

分析要求：
1. 核心主题：用简洁短语概括新闻核心投资逻辑
2. 情感倾向：利好(positive)/利空(negative)/中性(neutral)
3. 相关板块：映射到A股概念板块名称（2-3个）
4. 催化强度：0-10，越高代表对股价影响越大
5. 时间窗口：immediate（当天）/ short（1周内）/ medium（1-3月）
6. 推理说明：为什么这个主题现在值得关注

注意：
- 忽略纯宏观数据发布（如CPI、PMI），除非数据大幅超预期
- 关注产业、公司、政策类新闻
- 同一主题的多个新闻合并为一个信号，取最高催化强度

新闻：
{news_text}
"""


class NewsAnalyst:
    """Extract structured investment signals from news via LLM."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def scan(self) -> list[NewsSignal]:
        """Fetch news and extract signals via LLM."""
        # Fetch news
        news_items: list[dict] = []
        try:
            global_news = await self.collector.get_global_news(look_back_days=1, limit=30)
            if global_news:
                news_items.extend(global_news)
        except Exception as e:
            logger.warning("NewsAnalyst: global news failed: %s", e)

        try:
            from src.data.sources.cninfo_source import CninfoSource
            cninfo = CninfoSource(self.settings)
            announcements = await cninfo.get_announcements(limit=20)
            if announcements:
                news_items.extend(announcements)
        except Exception as e:
            logger.debug("NewsAnalyst: announcements failed: %s", e)

        if not news_items:
            logger.info("NewsAnalyst: no news items to analyze")
            return []

        # Batch process news (15 items per batch to stay within token limits)
        all_signals: list[NewsSignal] = []
        batch_size = 15
        for i in range(0, len(news_items), batch_size):
            batch = news_items[i:i + batch_size]
            batch_signals = await self._analyze_batch(batch)
            all_signals.extend(batch_signals)

        # Deduplicate by theme (keep highest catalyst_strength)
        seen: dict[str, NewsSignal] = {}
        for sig in all_signals:
            if sig.theme not in seen or sig.catalyst_strength > seen[sig.theme].catalyst_strength:
                seen[sig.theme] = sig

        final = sorted(seen.values(), key=lambda x: x.catalyst_strength, reverse=True)
        logger.info("NewsAnalyst: extracted %d unique signals", len(final))
        return final[:15]

    async def _analyze_batch(self, news_items: list[dict]) -> list[NewsSignal]:
        """Analyze a batch of news items via LLM."""
        news_text = "\n\n".join(
            f"[{item.get('source', '')}] {item.get('title', '')}\n{item.get('content', '')[:200]}"
            for item in news_items
        )

        prompt = _NEWS_ANALYSIS_PROMPT.format(news_text=news_text)

        try:
            analysis = await llm_structured_output(
                prompt=prompt,
                schema=NewsAnalysis,
                settings=self.settings,
            )
        except SectorDiscoveryLLMError:
            if not self.settings.sector_discovery_mock_mode:
                raise
            return []
        except Exception as e:
            logger.warning("NewsAnalyst: LLM analysis failed: %s", e)
            return []

        if not analysis or not analysis.signals:
            return []

        return [
            NewsSignal(
                theme=s.theme,
                sentiment=s.sentiment,
                related_sectors=s.related_sectors,
                catalyst_strength=s.catalyst_strength,
                time_window=s.time_window,
                source_headline=s.source_headline,
                reasoning=s.reasoning,
            )
            for s in analysis.signals
        ]
