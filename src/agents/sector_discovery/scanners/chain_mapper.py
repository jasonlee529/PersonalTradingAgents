"""ChainMapper — supply chain reasoning with LLM.

Identifies "downstream hot → upstream cold" expectation gap opportunities
using LLM-driven dynamic reasoning instead of hard-coded mapping tables.

Input: HotSignal[] (from MarketHeatScanner) + PolicySignal[] (from PolicyMiner)
Processing:
  1. For each hot concept, call LLM to reason upstream/midstream/downstream
  2. LLM outputs ChainAnalysis with segments + expectation-gap scores
  3. Match segment board_keywords to concept boards
  4. Fetch upstream-board stocks, score by price position
Output: ChainSignal[] with reasoning and board_keywords.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.llm_utils import llm_structured_output
from src.agents.sector_discovery.models import (
    ChainAnalysis,
    ChainSignal,
    HotSignal,
)
from src.agents.sector_discovery.policy_miner import PolicySignal
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


CHAIN_REASONING_PROMPT_TEMPLATE = """概念: {concept}

市场热度证据:
{evidence}

相关政策信号:
{policy_context}

请深入分析该概念的产业链上中下游各环节，评估每个环节的预期差（市场尚未充分认识的价值）。

输出要求:
- upstream: 材料/设备/零部件环节（预期差通常最大）
- midstream: 制造/集成环节（往往已有热度）
- downstream: 应用/运营环节（业绩兑现周期长）

对每个环节给出:
1. 环节名称
2. 产业链位置 (upstream/midstream/downstream)
3. 预期差评分 (0-10，越高越好)
4. 理由（为什么该环节有预期差）
5. 对应的 A 股概念板块关键词（用于匹配板块，如"铝塑膜"、"电池材料"）

最后列出预期差最大的 2-3 个环节名称。
"""


class ChainMapper:
    """Discover supply chain expectation gaps via LLM reasoning."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def analyze(
        self,
        hot_signals: list[HotSignal],
        policy_signals: list[PolicySignal],
    ) -> list[ChainSignal]:
        """Run LLM reasoning for each hot concept and map to upstream stocks."""
        if not hot_signals:
            logger.info("ChainMapper: no hot signals, skipping")
            return []

        results: list[ChainSignal] = []

        for hot in hot_signals:
            # Build policy context for this concept
            policy_context = self._build_policy_context(hot.concept, policy_signals)

            # LLM reasoning
            analysis = await self._llm_reason(hot, policy_context)
            if not analysis:
                continue

            # Map LLM segments to concept boards and fetch stocks
            chain_signals = await self._map_to_stocks(analysis)
            results.extend(chain_signals)

        logger.info("ChainMapper: returned %d chain signals", len(results))
        return results

    def _build_policy_context(
        self, concept: str, policy_signals: list[PolicySignal]
    ) -> str:
        """Find policy signals relevant to this concept."""
        relevant = []
        for sig in policy_signals:
            # Match by keyword or beneficiary industry
            if concept in sig.keyword or any(
                concept in ind for ind in sig.beneficiary_industries
            ):
                relevant.append(
                    f"- {sig.keyword} ({sig.level}级): {', '.join(sig.beneficiary_industries)} "
                    f"[时间窗口: {sig.time_window}, 置信度: {sig.confidence:.0%}]"
                )
        if not relevant:
            return "暂无直接相关政策信号。"
        return "\n".join(relevant)

    async def _llm_reason(
        self, hot: HotSignal, policy_context: str
    ) -> Optional[ChainAnalysis]:
        """Call LLM for supply-chain reasoning."""
        prompt = CHAIN_REASONING_PROMPT_TEMPLATE.format(
            concept=hot.concept,
            evidence=hot.evidence,
            policy_context=policy_context,
        )
        return await llm_structured_output(
            prompt=prompt,
            schema=ChainAnalysis,
            settings=self.settings,
        )

    async def _map_to_stocks(self, analysis: ChainAnalysis) -> list[ChainSignal]:
        """Map ChainAnalysis segments to concept boards and produce ChainSignals."""
        results: list[ChainSignal] = []

        try:
            boards = await self.collector.list_concept_boards(limit=300)
        except Exception as e:
            logger.warning("ChainMapper: list_concept_boards failed: %s", e)
            return results

        if not boards:
            return results

        # Score thresholds by position
        _THRESHOLDS = {
            "upstream": 4.0,
            "midstream": 3.5,
            "downstream": 3.0,
        }

        for segment in analysis.segments:
            threshold = _THRESHOLDS.get(segment.position, 4.0)

            # Match board keywords to concept boards
            matched_boards = self._match_boards(segment.board_keywords, boards)

            best_score = 0.0
            best_signal = None

            for board in matched_boards[:2]:  # Top 2 matched boards per segment
                board_code = board.get("code", "")
                board_name = board.get("name", "")
                if not board_code:
                    continue

                try:
                    stocks = await self.collector.get_board_stocks(board_code, limit=20)
                except Exception as e:
                    logger.debug("ChainMapper: board %s failed: %s", board_code, e)
                    continue

                if not stocks:
                    continue

                for item in stocks[:10]:
                    symbol = item.get("symbol", "")
                    name = item.get("name", "")
                    change_pct_raw = item.get("change_pct", 0)
                    if not symbol:
                        continue

                    try:
                        change_pct = float(change_pct_raw)
                    except (TypeError, ValueError):
                        change_pct = 0.0

                    # Low price change = higher expectation gap
                    price_factor = max(0, 10 - abs(change_pct)) / 10.0
                    score = round(segment.expectation_gap_score * price_factor, 1)

                    if score < threshold:
                        continue

                    if score > best_score:
                        best_score = score
                        best_signal = ChainSignal(
                            concept=analysis.concept,
                            segment_name=segment.name,
                            position=segment.position,
                            expectation_gap_score=score,
                            reasoning=f"{segment.reasoning} 板块: {board_name}",
                            board_keywords=segment.board_keywords,
                        )

            if best_signal:
                results.append(best_signal)

        # Deduplicate by (concept, segment_name) keeping highest score
        seen: dict[str, ChainSignal] = {}
        for cs in results:
            key = f"{cs.concept}:{cs.segment_name}"
            if key not in seen or cs.expectation_gap_score > seen[key].expectation_gap_score:
                seen[key] = cs

        return sorted(seen.values(), key=lambda x: x.expectation_gap_score, reverse=True)

    def _match_boards(
        self, keywords: list[str], boards: list[dict]
    ) -> list[dict]:
        """Match segment board_keywords to concept boards."""
        scored: list[tuple[float, dict]] = []
        for board in boards:
            name = board.get("name", "")
            score = 0.0
            for kw in keywords:
                if kw in name:
                    score += 3.0  # Strong match
                elif any(c in name for c in kw):
                    score += 1.0  # Weak match
            if score > 0:
                scored.append((score, board))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [b for _, b in scored]

