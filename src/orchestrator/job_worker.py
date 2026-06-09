# src/orchestrator/job_worker.py
import asyncio
import logging
import signal

from src.config import Settings, load_settings_from_env_file
from src.data.cache import DataCache
from src.knowledge.raw_store import RawStore
from src.orchestrator.job_store import JobStore
from src.orchestrator.pipeline import AnalysisPipeline
from src.portfolio.manager import PortfolioManager
from src.utils.logger import logging_context, setup_logging

logger = logging.getLogger(__name__)


class AnalysisJobWorker:
    def __init__(self, settings: Settings, poll_interval: float = 1.0):
        self.settings = settings
        self.poll_interval = poll_interval
        self.cache = DataCache(settings)
        self.portfolio = PortfolioManager(settings)
        self.raw_store = RawStore(settings)
        self.job_store = JobStore(settings.analysis_db_path)
        self.pipeline: AnalysisPipeline | None = None
        self._stop = asyncio.Event()

    async def init(self) -> None:
        self.settings.ensure_dirs()
        await self.cache.init_db()
        await self.portfolio.init_db()
        await self.raw_store.init_db()
        await self.job_store.init_db()
        self.pipeline = AnalysisPipeline(
            settings=self.settings,
            cache=self.cache,
            portfolio=self.portfolio,
            job_store=self.job_store,
            raw_store=self.raw_store,
        )

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        if self.pipeline is None:
            await self.init()

        logger.info("Analysis job worker started")
        try:
            reclaimed = await self.job_store.reclaim_stale_jobs()
            if reclaimed:
                logger.info("Reclaimed %d stale running jobs: %s", len(reclaimed), reclaimed)
        except Exception:
            logger.exception("Failed to reclaim stale jobs")
        while not self._stop.is_set():
            try:
                job = await self.job_store.claim_next_pending()
                if job is None:
                    await asyncio.sleep(self.poll_interval)
                    continue

                await self._run_job(job)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Analysis job worker loop error")
                await asyncio.sleep(self.poll_interval)
        logger.info("Analysis job worker stopped")

    async def _run_job(self, job) -> None:
        assert self.pipeline is not None
        with logging_context(job_id=job.id, symbol=job.symbol):
            try:
                # Reload settings from .env so UI changes are picked up even if
                # this child process inherited stale environment variables.
                fresh_settings = load_settings_from_env_file()
                self.settings = fresh_settings
                self.cache = DataCache(fresh_settings)
                self.portfolio = PortfolioManager(fresh_settings)
                self.raw_store = RawStore(fresh_settings)
                self.job_store = JobStore(fresh_settings.analysis_db_path)
                await self.cache.init_db()
                await self.portfolio.init_db()
                await self.raw_store.init_db()
                await self.job_store.init_db()
                self.pipeline = AnalysisPipeline(
                    settings=fresh_settings,
                    cache=self.cache,
                    portfolio=self.portfolio,
                    job_store=self.job_store,
                    raw_store=self.raw_store,
                )

                cfg = job.config or {}
                config_overrides = {
                    k: v for k, v in cfg.items()
                    if k in (
                        "output_language",
                        "llm_provider",
                        "research_depth",
                        "thinking_agents",
                        "trade_date",
                    )
                } or None
                await self.pipeline.run_single(
                    job.symbol,
                    selected_analysts=cfg.get("analysts"),
                    config_overrides=config_overrides,
                    job=job,
                )
                if job.status.value == "done":
                    return
                job.fail("Pipeline completed but status is not done")
                await self.job_store.save(job)
            except Exception as e:
                logger.exception("Job execution failed")
                job.fail(str(e))
                await self.job_store.save(job)


async def _main() -> None:
    settings = load_settings_from_env_file()
    setup_logging(log_dir=settings.data_dir / "logs", log_name="analysis_worker.log", console=False)
    worker = AnalysisJobWorker(settings)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            pass

    await worker.run_forever()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
