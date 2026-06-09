"""PolicyScout — policy-driven beneficiary discovery with ChainMapper linkage.

Scans for "policy just announced, market hasn't fully recognized yet" opportunities
by cross-matching PolicyMiner signals with ChainMapper upstream segments.

Input: PolicySignal[] (from PolicyMiner) + ChainSignal[] (from ChainMapper)
Processing:
  1. Cross-match: PolicySignal.beneficiary_industries ∩ ChainSignal.segment_name/board_keywords
  2. For matched upstream segments, fetch constituent stocks
  3. Score by policy level + upstream position + low price movement
Output: StockSignal list with policy dimension.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.agents.sector_discovery.models import ChainSignal, StockSignal
from src.agents.sector_discovery.policy_miner import PolicySignal
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)

# Policy level score bonus
LEVEL_BONUS = {
    "国务院": 3.0,
    "部委": 2.0,
    "地方": 1.0,
}

# Position bonus
POSITION_BONUS = {
    "upstream": 2.0,
    "midstream": 1.0,
    "downstream": 0.0,
}

_DEFAULT_PRICE_CHANGE_THRESHOLD = 10.0


class PolicyScout:
    """Discover policy-driven opportunities before market recognition."""

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    async def scan(
        self,
        policy_signals: list[PolicySignal],
        chain_signals: list[ChainSignal] | None = None,
    ) -> list[StockSignal]:
        """Cross-match policy signals with upstream chain segments and pick stocks."""
        if not policy_signals:
            logger.info("PolicyScout: no policy signals, skipping")
            return []

        # Cross-match
        if chain_signals:
            matched = self._cross_match(policy_signals, chain_signals)
        else:
            matched = self._standalone_match(policy_signals)
        if not matched:
            logger.info("PolicyScout: no policy-chain cross-match found")
            return []

        logger.info("PolicyScout: %d policy-chain matches", len(matched))

        # Fetch stocks for matched segments
        results: list[StockSignal] = []
        seen_boards: set[str] = set()

        for policy_sig, chain_sig in matched:
            # Find board by chain_sig board_keywords
            board = await self._find_board(chain_sig.board_keywords)
            if not board:
                continue

            board_code = board.get("code", "")
            board_name = board.get("name", "")
            if not board_code or board_code in seen_boards:
                continue
            seen_boards.add(board_code)

            try:
                stocks = await self.collector.get_board_stocks(board_code, limit=20)
            except Exception as e:
                logger.debug("PolicyScout: board %s failed: %s", board_code, e)
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

                # Skip if already moved too much
                if abs(change_pct) > _DEFAULT_PRICE_CHANGE_THRESHOLD:
                    continue

                score = self._compute_score(policy_sig, chain_sig, change_pct)

                reason_parts = [
                    f"{policy_sig.keyword}政策受益",
                    f"产业链{chain_sig.position}: {chain_sig.segment_name}",
                ]
                if policy_sig.level:
                    reason_parts.append(f"政策级别: {policy_sig.level}")
                reason_parts.append(f"当日涨幅 {change_pct or 0}%")

                results.append(
                    StockSignal(
                        symbol=symbol,
                        name=name,
                        score=round(score, 1),
                        dimension="policy",
                        reason="，".join(reason_parts),
                        catalyst=f"关注{policy_sig.keyword}政策细则落地",
                        time_horizon="medium",
                        metadata={
                            "policy_level": policy_sig.level,
                            "position": chain_sig.position,
                            "expectation_gap_score": chain_sig.expectation_gap_score,
                            "price_change": change_pct,
                            "policy_keyword": policy_sig.keyword,
                            "beneficiary_industries": policy_sig.beneficiary_industries,
                            "policy_time_window": policy_sig.time_window,
                        },
                    )
                )

        # Deduplicate by symbol (keep highest score)
        seen: dict[str, StockSignal] = {}
        for s in results:
            if s.symbol not in seen or s.score > seen[s.symbol].score:
                seen[s.symbol] = s

        final = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        logger.info("PolicyScout: returned %d unique signals", len(final))
        return final

    def _cross_match(
        self,
        policy_signals: list[PolicySignal],
        chain_signals: list[ChainSignal],
    ) -> list[tuple[PolicySignal, ChainSignal]]:
        """Match policy beneficiary industries with chain segments."""
        matched: list[tuple[PolicySignal, ChainSignal]] = []

        for ps in policy_signals:
            beneficiaries = set(ps.beneficiary_industries)
            for cs in chain_signals:
                # Match by segment name or board keywords
                segment_tokens = {cs.segment_name} | set(cs.board_keywords)
                if beneficiaries & segment_tokens:
                    matched.append((ps, cs))
                    continue
                # Fuzzy match: any beneficiary keyword appears in segment tokens
                for ben in beneficiaries:
                    for token in segment_tokens:
                        if ben in token or token in ben:
                            matched.append((ps, cs))
                            break
                    else:
                        continue
                    break

        # Sort by combined confidence + expectation gap
        matched.sort(
            key=lambda pair: pair[0].confidence + pair[1].expectation_gap_score / 10,
            reverse=True,
        )
        return matched[:15]  # Limit cross-match pairs

    def _standalone_match(
        self,
        policy_signals: list[PolicySignal],
    ) -> list[tuple[PolicySignal, ChainSignal]]:
        """Match policy signals directly to concept boards without chain signals."""
        matched: list[tuple[PolicySignal, ChainSignal]] = []
        for ps in policy_signals:
            for industry in ps.beneficiary_industries:
                # Create a synthetic ChainSignal for matching
                synthetic = ChainSignal(
                    concept=ps.keyword,
                    segment_name=industry,
                    position="midstream",
                    expectation_gap_score=5.0,
                    reasoning=f"政策受益行业: {industry}",
                    board_keywords=[industry],
                )
                matched.append((ps, synthetic))
        # Sort by policy confidence
        matched.sort(key=lambda pair: pair[0].confidence, reverse=True)
        return matched[:15]

    async def _find_board(self, board_keywords: list[str]) -> Optional[dict]:
        """Find a concept board matching the given keywords."""
        try:
            boards = await self.collector.list_concept_boards(limit=300)
        except Exception as e:
            logger.warning("PolicyScout: list_concept_boards failed: %s", e)
            return None

        if not boards:
            return None

        best: Optional[tuple[float, dict]] = None
        for board in boards:
            name = board.get("name", "")
            score = 0.0
            for kw in board_keywords:
                if kw in name:
                    score += 3.0
                elif any(c in name for c in kw):
                    score += 1.0
            if score > 0 and (best is None or score > best[0]):
                best = (score, board)

        return best[1] if best else None

    def _compute_score(
        self, policy_sig: PolicySignal, chain_sig: ChainSignal, change_pct: float
    ) -> float:
        """Score by policy level + upstream position + low price movement."""
        base = 5.0

        # Policy level bonus
        base += LEVEL_BONUS.get(policy_sig.level, 0.0)

        # Upstream position bonus
        base += POSITION_BONUS.get(chain_sig.position, 0.0)

        # Low price movement = more mismatch potential
        move = abs(change_pct or 0)
        if move < 5.0:
            base += 2.0
        elif move < 10.0:
            base += 1.0

        # Expectation gap from ChainMapper
        base += chain_sig.expectation_gap_score * 0.3

        return min(base, 10.0)
