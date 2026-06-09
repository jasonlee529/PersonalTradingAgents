"""Sector Discovery Agent — daily direction recommendation system.

Five-dimensional parallel scanning:
- MarketHeatScanner: momentum + fund flow
- PolicyScout: policy-driven beneficiaries
- FundAnalyst: institutional mispricing
- ValueDigger: fundamentals at discount
- ChainMapper: supply-chain expectation gaps

Pipeline: PolicyMiner → 5 Scanners → SectorAggregator → SectorRanker → StockScreener → DirectionReport
"""

from src.agents.sector_discovery.pipeline import SectorDiscoveryPipeline
from src.agents.sector_discovery.policy_miner import PolicyMiner, PolicySignal
from src.agents.sector_discovery.scanners.base import SectorScanner, ScanResult

__all__ = [
    "SectorDiscoveryPipeline",
    "PolicyMiner",
    "PolicySignal",
    "SectorScanner",
    "ScanResult",
]

