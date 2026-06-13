# src/orchestrator/job_worker.py
import asyncio
import logging
import signal
import time

from src.config import Settings, load_settings_from_env_file
from src.data.cache import DataCache
from src.knowledge.raw_store import RawStore
from src.orchestrator.job_store import JobStore
from src.orchestrator.pipeline import AnalysisPipeline
from src.orchestrator.state import JobStatus
from src.portfolio.manager import PortfolioManager
from src.utils.logger import logging_context, setup_logging

logger = logging.getLogger(__name__)

# How often (seconds) to sweep for stale running jobs in the main loop.
_STALE_RECLAIM_INTERVAL = 120


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
        # Track the currently running job so we can mark it failed on SIGTERM.
        self._current_job_id: str | None = None
        self._current_job_symbol: str | None = None

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

    async def _mark_current_job_failed(self, reason: str) -> None:
        """Best-effort attempt to mark the in-flight job as ERROR so it
        doesn't stay stuck in 'running' state after the worker dies."""
        if not self._current_job_id:
            return
        try:
            job = await self.job_store.get(self._current_job_id)
            if job and job.status == JobStatus.RUNNING:
                job.fail(reason)
                await self.job_store.save(job)
                logger.warning(
                    "Marked stale job %s (%s) as ERROR: %s",
                    self._current_job_id,
                    self._current_job_symbol,
                    reason,
                )
        except Exception:
            logger.exception(
                "Failed to mark job %s as failed during shutdown",
                self._current_job_id,
            )

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

        last_reclaim = time.monotonic()
        while not self._stop.is_set():
            try:
                job = await self.job_store.claim_next_pending()
                if job is None:
                    await asyncio.sleep(self.poll_interval)
                    # Periodic stale-job sweep so orphaned jobs get
                    # reclaimed even if the worker stays alive.
                    now = time.monotonic()
                    if now - last_reclaim >= _STALE_RECLAIM_INTERVAL:
                        try:
                            reclaimed = await self.job_store.reclaim_stale_jobs()
                            if reclaimed:
                                logger.info(
                                    "Periodic reclaim: %d stale jobs: %s",
                                    len(reclaimed),
                                    reclaimed,
                                )
                        except Exception:
                            logger.exception("Periodic stale-job reclaim failed")
                        last_reclaim = now
                    continue

                self._current_job_id = job.id
                self._current_job_symbol = job.symbol
                await self._run_job(job)
                self._current_job_id = None
                self._current_job_symbol = None
            except asyncio.CancelledError:
                # Graceful async cancellation — try to mark the job.
                await self._mark_current_job_failed("Worker cancelled")
                break
            except Exception:
                logger.exception("Analysis job worker loop error")
                await asyncio.sleep(self.poll_interval)

        self._current_job_id = None
        self._current_job_symbol = None
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
                # Don't overwrite a meaningful error message already set by
                # the pipeline (e.g. "Analysis timed out after 600s") with
                # str(e) which may be empty (e.g. str(asyncio.TimeoutError) == '').
                if not job.error:
                    job.fail(str(e))
                await self.job_store.save(job)


async def _main() -> None:
    settings = load_settings_from_env_file()
    setup_logging(log_dir=settings.data_dir / "logs", log_name="analysis_worker.log", console=False)
    worker = AnalysisJobWorker(settings)

    loop = asyncio.get_running_loop()

    def _on_signal():
        """SIGTERM / SIGINT handler — mark in-flight job as failed, then stop the loop."""
        # Schedule async cleanup in the event loop.
        loop.create_task(worker._mark_current_job_failed("Worker received termination signal"))
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler; rely on
            # reclaim_stale_jobs for cleanup instead.
            pass

    await worker.run_forever()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()