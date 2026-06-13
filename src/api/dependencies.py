import datetime
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from fastapi import Request

from src.config import Settings
from src.config import PERSISTED_SETTINGS_FIELDS
from src.data.cache import DataCache
from src.portfolio.manager import PortfolioManager
from src.portfolio.trade_recorder import TradeRecorder
from src.portfolio.orchestrator import PortfolioDrivenOrchestrator
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_ingest_queue import WikiIngestQueue
from src.knowledge.wiki_store import WikiStore
from src.orchestrator.job_store import JobStore
from src.orchestrator.scheduler import AnalysisScheduler
from src.data.collector import DataCollector
from src.news.collector import NewsCollector

logger = logging.getLogger(__name__)


class _TimestampedLogWriter:
    """Wrap a file handle and prefix each line with an ISO timestamp."""

    def __init__(self, path: Path):
        self._fh = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, data: str) -> None:
        if not data:
            return
        with self._lock:
            now = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
            lines = data.splitlines(keepends=True)
            for line in lines:
                # Only prefix if the line isn't already timestamped
                if line.strip() and not line.startswith("20"):
                    self._fh.write(f"{now} | {line}")
                else:
                    self._fh.write(line)
            self._fh.flush()

    def flush(self) -> None:
        self._fh.flush()

    def fileno(self) -> int:
        return self._fh.fileno()

    def close(self) -> None:
        self._fh.close()


class AppServices:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache = DataCache(settings)
        self.portfolio = PortfolioManager(settings)
        self.raw_store = RawStore(settings)
        self.wiki_store = WikiStore(settings)
        self.wiki_ingest_queue = WikiIngestQueue(settings, self.raw_store, self.wiki_store)
        self.trade_recorder = TradeRecorder(self.portfolio, self.raw_store)
        self.job_store = JobStore(settings.analysis_db_path)
        self.collector = DataCollector(settings, self.cache)
        self.news_collector = NewsCollector(settings, self.cache, self.portfolio)
        self.portfolio_orchestrator = PortfolioDrivenOrchestrator(
            settings=settings,
            analysis_pipeline=None,
        )
        self.scheduler = AnalysisScheduler(
            settings=settings,
            job_store=self.job_store,
            collector=self.collector,
            portfolio=self.portfolio,
        )
        self._worker_process: subprocess.Popen | None = None
        self._worker_log_handles = []

    async def init(self) -> None:
        self.settings.ensure_dirs()
        await self.cache.init_db()
        await self.portfolio.init_db()
        await self.raw_store.init_db()
        await self.wiki_store.init_db()
        if getattr(self.collector, "_historical_store", None) is not None:
            await self.collector._historical_store.ensure_db()
        await self.wiki_ingest_queue.recover_interrupted()
        await self.job_store.init_db()
        await self.scheduler.load_tasks()
        # Register orchestrator as portfolio listener
        self.portfolio.add_listener(self.portfolio_orchestrator.on_portfolio_event)

    def start_job_worker(self) -> None:
        """Start the analysis worker in a separate process."""
        if not self.settings.analysis_worker_enabled:
            logger.info("Analysis worker disabled")
            return
        if self._worker_process and self._worker_process.poll() is None:
            return

        repo_root = Path(__file__).resolve().parents[2]
        log_dir = self.settings.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = _TimestampedLogWriter(log_dir / "analysis_worker.out.log")
        stderr = _TimestampedLogWriter(log_dir / "analysis_worker.err.log")
        self._worker_log_handles = [stdout, stderr]

        env = self._worker_env(repo_root)
        self._worker_process = subprocess.Popen(
            [sys.executable, "-m", "src.orchestrator.job_worker"],
            cwd=repo_root,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        logger.info("Analysis worker process started pid=%s", self._worker_process.pid)

    def start_scheduler(self) -> None:
        if getattr(self.settings, "scheduler_enabled", False):
            self.scheduler.start()

    def start_wiki_ingest_queue(self) -> None:
        self.wiki_ingest_queue.start()

    def stop_wiki_ingest_queue(self) -> None:
        self.wiki_ingest_queue.stop()

    def stop_scheduler(self) -> None:
        self.scheduler.stop()

    def stop_job_worker(self) -> None:
        """Stop the analysis worker process."""
        if not self._worker_process:
            return
        if self._worker_process.poll() is None:
            self._worker_process.terminate()
            try:
                self._worker_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self._worker_process.kill()
                self._worker_process.wait(timeout=10)
            logger.info("Analysis worker process stopped pid=%s", self._worker_process.pid)
        self._worker_process = None
        for handle in self._worker_log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self._worker_log_handles = []

    def restart_job_worker(self) -> None:
        """Restart the worker so runtime settings changes reach its process env."""
        if not self.settings.analysis_worker_enabled:
            return
        self.stop_job_worker()
        self.start_job_worker()

    def _worker_env(self, repo_root: Path) -> dict[str, str]:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(repo_root)
            if not existing_pythonpath
            else str(repo_root) + os.pathsep + existing_pythonpath
        )
        path_fields = (
            "data_dir",
            "knowledge_dir",
            "raw_knowledge_dir",
            "raw_knowledge_db_path",
            "wiki_knowledge_dir",
            "wiki_knowledge_db_path",
            "wiki_schema_dir",
            "derived_knowledge_dir",
            "derived_knowledge_db_path",
            "cache_db_path",
            "portfolio_db_path",
            "analysis_db_path",
            "historical_db_path",
            "runtime_cache_dir",
            "analysis_artifacts_dir",
            "checkpoint_dir",
        )
        for field in path_fields:
            env[field.upper()] = str(getattr(self.settings, field))
        for field, env_var in PERSISTED_SETTINGS_FIELDS.items():
            value = getattr(self.settings, field, None)
            if value is None:
                continue
            env[env_var] = "true" if value is True else "false" if value is False else str(value)
        return env


async def get_services(request: Request) -> AppServices:
    return request.app.state.services


async def get_settings(request: Request) -> Settings:
    return request.app.state.services.settings
