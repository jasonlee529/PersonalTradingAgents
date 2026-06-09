"""Base class for all sector scanners."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from src.agents.sector_discovery.models import StockSignal
from src.config import Settings
from src.data.cache import DataCache
from src.data.collector import DataCollector

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result from a single scanner dimension."""
    dimension: str  # e.g. "market_heat"
    stocks: list[StockSignal] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)


class SectorScanner(ABC):
    """Base class for sector discovery scanners.

    Each scanner implements a single dimension of analysis
    (Market heat, policy, fund, value, supply chain).
    Scanners run in parallel via asyncio.gather.
    """

    def __init__(
        self,
        settings: Settings,
        cache: DataCache,
        data_collector: Optional[DataCollector] = None,
    ):
        self.settings = settings
        self.cache = cache
        self.collector = data_collector or DataCollector(settings, cache)

    @property
    @abstractmethod
    def dimension(self) -> str:
        """Human-readable dimension name."""
        ...

    @abstractmethod
    async def scan(self, board_code: Optional[str] = None) -> ScanResult:
        """Execute the scan. If board_code is given, narrow to that board.

        Returns ScanResult with stocks ranked by this dimension's logic.
        """
        ...

