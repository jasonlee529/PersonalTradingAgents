import asyncio
import logging
from src.data.collector import DataCollector
from src.portfolio.manager import PortfolioManager
from src.portfolio.models import DataStatus

logger = logging.getLogger(__name__)


class DataCollectionService:
    """Collects historical data for newly added holdings in background."""

    def __init__(self, collector: DataCollector, portfolio: PortfolioManager):
        self.collector = collector
        self.portfolio = portfolio

    async def collect_for_symbol(self, symbol: str) -> None:
        """Fetch full snapshot and update status."""
        logger.info("Starting data collection for %s", symbol)
        await self.portfolio.update_data_status(symbol, DataStatus.COLLECTING)
        try:
            snapshot = await self.collector.get_full_snapshot(symbol)
            if snapshot.get("quote") or snapshot.get("kline"):
                await self.portfolio.update_data_status(symbol, DataStatus.READY)
                logger.info("Data collection complete for %s", symbol)
            else:
                await self.portfolio.update_data_status(symbol, DataStatus.ERROR)
                logger.warning("Data collection returned empty for %s", symbol)
        except Exception as e:
            await self.portfolio.update_data_status(symbol, DataStatus.ERROR)
            logger.error("Data collection failed for %s: %s", symbol, e)

    def start_collection(self, symbol: str) -> asyncio.Task:
        """Start collection in background. Returns the task."""
        task = asyncio.create_task(self.collect_for_symbol(symbol))
        return task
