import logging
from typing import Optional

from src.config import Settings

logger = logging.getLogger(__name__)


class PortfolioDrivenOrchestrator:
    """React to portfolio changes: log events and optionally trigger analysis."""

    def __init__(
        self,
        settings: Settings,
        analysis_pipeline: Optional = None,
    ):
        self.settings = settings
        self.analysis_pipeline = analysis_pipeline

    async def on_portfolio_event(self, event_type: str, symbol: str) -> None:
        """Handle portfolio add/remove events."""
        if event_type == "added":
            await self._on_holding_added(symbol)
        elif event_type == "removed":
            await self._on_holding_removed(symbol)
        else:
            logger.debug("Ignoring unknown portfolio event: %s", event_type)

    async def _on_holding_added(self, symbol: str) -> None:
        """Log new holding and optionally trigger analysis."""
        logger.info("New holding added: %s", symbol)

        if self.settings.wiki_auto_analysis_enabled and self.analysis_pipeline:
            logger.info("Auto-triggering analysis for %s", symbol)
            try:
                await self.analysis_pipeline.run_single(symbol)
            except Exception as e:
                logger.error("Auto-analysis failed for %s: %s", symbol, e)

    async def _on_holding_removed(self, symbol: str) -> None:
        """Log holding removal."""
        logger.info("Holding removed: %s", symbol)
