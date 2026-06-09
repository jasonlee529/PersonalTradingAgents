import logging
from typing import Any, Optional

from src.config import Settings

logger = logging.getLogger(__name__)


class DailyInspectionJob:
    """Scheduled daily inspection: optional auto-analysis only.

    News ingestion is handled by the raw auto collector.
    """

    def __init__(
        self,
        settings: Settings,
        analysis_pipeline: Optional[Any] = None,
    ):
        self.settings = settings
        self.analysis_pipeline = analysis_pipeline

    async def run(self) -> dict:
        """Run daily inspection.

        Returns a summary dict.
        """
        if not self.settings.wiki_auto_analysis_enabled or not self.analysis_pipeline:
            logger.info("Daily inspection skipped: auto-analysis disabled")
            return {"skipped": True}

        logger.info("Daily inspection: starting auto-analysis")
        try:
            jobs = await self.analysis_pipeline.run_all()
            analysis_result = {
                "jobs_count": len(jobs),
                "symbols": [j.symbol for j in jobs],
            }
        except Exception as e:
            logger.error("Daily inspection auto-analysis failed: %s", e)
            analysis_result = {"error": str(e)}

        return {
            "analysis_ran": "error" not in analysis_result,
            "analysis": analysis_result,
        }
