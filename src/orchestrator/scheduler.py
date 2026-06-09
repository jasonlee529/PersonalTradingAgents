# src/orchestrator/scheduler.py
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import Settings
from src.orchestrator.job_store import JobStore

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    id: str
    name: str
    description: str
    enabled: bool
    cron: str
    handler_factory: Callable[[], "TaskHandler"]


class TaskHandler(ABC):
    @abstractmethod
    async def run(self) -> dict:
        """Execute the scheduled task. Return a result dict."""
        ...


_DEFAULT_TASKS: list[dict] = [
    {
        "id": "analysis",
        "name": "AI 分析",
        "description": "对持仓股票运行 AI 多智能体分析",
        "enabled": False,
        "cron": "0 9 * * 1-5",
    },
    {
        "id": "data_refresh",
        "name": "持仓数据刷新",
        "description": "刷新持仓股票的历史 K 线数据",
        "enabled": False,
        "cron": "0 6 * * 1-5",
    },
    {
        "id": "sector_discovery",
        "name": "今日方向",
        "description": "扫描板块热度、政策信号和资金偏好",
        "enabled": False,
        "cron": "0 8 * * 1-5",
    },
]


class AnalysisHandler(TaskHandler):
    """Stub handler for scheduled AI analysis."""

    def __init__(self, pipeline: Any = None):
        self.pipeline = pipeline

    async def run(self) -> dict:
        logger.info("Scheduled analysis triggered")
        if self.pipeline is None:
            return {"success": False, "message": "Analysis pipeline not available"}
        try:
            jobs = await self.pipeline.run_all()
            return {"success": True, "message": f"Analyzed {len(jobs)} holdings"}
        except Exception as e:
            logger.error("Scheduled analysis failed: %s", e)
            return {"success": False, "message": str(e)}


class DataRefreshHandler(TaskHandler):
    """Stub handler for scheduled data refresh."""

    def __init__(self, collector: Any = None, portfolio: Any = None):
        self.collector = collector
        self.portfolio = portfolio

    async def run(self) -> dict:
        logger.info("Scheduled data refresh triggered")
        if not self.collector or not self.portfolio:
            return {"success": False, "message": "Collector or portfolio not available"}
        try:
            holdings = await self.portfolio.list_holdings()
            if not holdings:
                return {"success": True, "message": "No holdings to refresh"}
            count = 0
            for h in holdings:
                symbol = h.symbol
                data = await self.collector._fetch_with_fallback(
                    "kline", "get_kline", symbol, period="1d", limit=120
                )
                if data and self.collector._historical_store:
                    await self.collector._historical_store.save_kline(symbol, "1d", data)
                    count += 1
            return {"success": True, "message": f"Refreshed {count} holdings"}
        except Exception as e:
            logger.error("Scheduled data refresh failed: %s", e)
            return {"success": False, "message": str(e)}


class SectorDiscoveryHandler(TaskHandler):
    """Handler for scheduled sector discovery with notification push."""

    def __init__(self, settings: Any = None):
        self.settings = settings

    async def run(self) -> dict:
        logger.info("Scheduled sector discovery triggered")
        if not self.settings:
            return {"success": True, "message": "Sector discovery stub - not yet implemented"}

        try:
            # Import here to avoid circular imports at module level
            from src.data.cache import DataCache
            from src.data.collector import DataCollector
            from src.agents.sector_discovery.coordinator import Coordinator
            from src.agents.sector_discovery.models import DirectionContext
            from src.knowledge.raw_store import RawStore
            from src.services.notification import NotificationService
            from src.utils.trading_dates import normalize_trade_date

            cache = DataCache(self.settings)
            await cache.init_db()
            collector = DataCollector(self.settings, cache)
            trade_date = normalize_trade_date(datetime.now().strftime("%Y-%m-%d"))
            context = DirectionContext(
                date=trade_date,
                market_overview={},
                news_context="",
            )
            coordinator = Coordinator(self.settings, cache, collector)
            report = await coordinator.run(context=context)

            # Persist to raw store
            raw_store = RawStore(self.settings)
            await raw_store.init_db()
            tags = list({t for s in report.sectors for t in s.tags})
            result = await raw_store.add_source(
                source_kind="daily_direction",
                origin="agent",
                title=f"{report.date} 今日方向",
                markdown=report.to_markdown(),
                metadata={
                    "summary": report.summary,
                    "trade_date": report.date,
                    "tags": tags,
                    "sector_count": len(report.sectors),
                    "run_id": f"scheduled_{trade_date}",
                },
            )
            logger.info(
                "Scheduled sector discovery completed: date=%s sectors=%d",
                report.date, len(report.sectors),
            )

            # Push notification if enabled
            if getattr(self.settings, "daily_direction_notification_enabled", False):
                try:
                    notifier = NotificationService(self.settings)
                    rel_path = result.get("content_path", "")
                    if rel_path:
                        push_result = await notifier.push_raw(
                            rel_path,
                            route_type="report",
                        )
                        if push_result.success:
                            logger.info("Notification pushed to %d channels", len(push_result.channel_results))
                        else:
                            logger.warning("Notification push failed: %s", push_result.message)
                except Exception as notify_err:
                    logger.error("Notification push error: %s", notify_err)

            return {
                "success": True,
                "message": f"Sector discovery completed: {len(report.sectors)} directions",
                "sectors": len(report.sectors),
            }
        except Exception as e:
            logger.error("Scheduled sector discovery failed: %s", e)
            return {"success": False, "message": str(e)}


class AnalysisScheduler:
    """Registry-based multi-task scheduler using APScheduler."""

    def __init__(
        self,
        settings: Settings,
        job_store: JobStore,
        pipeline: Any = None,
        collector: Any = None,
        portfolio: Any = None,
    ):
        self.settings = settings
        self.job_store = job_store
        self.pipeline = pipeline
        self.collector = collector
        self.portfolio = portfolio
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._tasks: dict[str, ScheduledTask] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        self._tasks["analysis"] = ScheduledTask(
            id="analysis",
            name="AI 分析",
            description="对持仓股票运行 AI 多智能体分析",
            enabled=False,
            cron="0 9 * * 1-5",
            handler_factory=lambda: AnalysisHandler(self.pipeline),
        )
        self._tasks["data_refresh"] = ScheduledTask(
            id="data_refresh",
            name="持仓数据刷新",
            description="刷新持仓股票的历史 K 线数据",
            enabled=False,
            cron="0 6 * * 1-5",
            handler_factory=lambda: DataRefreshHandler(self.collector, self.portfolio),
        )
        self._tasks["sector_discovery"] = ScheduledTask(
            id="sector_discovery",
            name="今日方向",
            description="扫描板块热度、政策信号和资金偏好",
            enabled=False,
            cron="0 8 * * 1-5",
            handler_factory=lambda: SectorDiscoveryHandler(self.settings),
        )

    async def load_tasks(self) -> list[dict]:
        """Load task configs from DB; seed defaults if table is empty."""
        db_tasks = await self.job_store.list_scheduled_tasks()
        if not db_tasks:
            # Seed from legacy settings on first run
            legacy_analysis_enabled = getattr(self.settings, "scheduler_enabled", False)
            legacy_cron = getattr(self.settings, "analysis_schedule", "0 9 * * 1-5")
            for defaults in _DEFAULT_TASKS:
                task = dict(defaults)
                if task["id"] == "analysis":
                    task["enabled"] = legacy_analysis_enabled
                    task["cron"] = legacy_cron
                await self.job_store.save_scheduled_task(task)
            db_tasks = await self.job_store.list_scheduled_tasks()

        # Overlay DB config onto registered tasks
        for row in db_tasks:
            tid = row["id"]
            if tid in self._tasks:
                self._tasks[tid] = ScheduledTask(
                    id=tid,
                    name=row.get("name", self._tasks[tid].name),
                    description=row.get("description", self._tasks[tid].description),
                    enabled=row.get("enabled", False),
                    cron=row.get("cron", self._tasks[tid].cron),
                    handler_factory=self._tasks[tid].handler_factory,
                )
        return self.list_tasks()

    def is_running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def start(self) -> None:
        if self._scheduler and self._scheduler.running:
            return
        self._scheduler = AsyncIOScheduler()
        for task in self._tasks.values():
            if not task.enabled:
                continue
            try:
                trigger = CronTrigger.from_crontab(task.cron)
            except ValueError:
                logger.warning("Invalid cron for %s (%s), skipping", task.id, task.cron)
                continue
            self._scheduler.add_job(
                self._make_job_wrapper(task),
                trigger=trigger,
                id=f"scheduled_{task.id}",
                name=task.name,
                replace_existing=True,
            )
            logger.info("Registered scheduled job %s with cron %s", task.id, task.cron)
        self._scheduler.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            logger.info("Scheduler stopped")

    def list_tasks(self) -> list[dict]:
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "enabled": t.enabled,
                "cron": t.cron,
            }
            for t in self._tasks.values()
        ]

    async def update_task(self, task_id: str, enabled: Optional[bool] = None, cron: Optional[str] = None) -> None:
        if task_id not in self._tasks:
            raise ValueError(f"Unknown task: {task_id}")
        task = self._tasks[task_id]
        if enabled is not None:
            task = ScheduledTask(
                id=task.id,
                name=task.name,
                description=task.description,
                enabled=enabled,
                cron=task.cron,
                handler_factory=task.handler_factory,
            )
        if cron is not None:
            task = ScheduledTask(
                id=task.id,
                name=task.name,
                description=task.description,
                enabled=task.enabled,
                cron=cron,
                handler_factory=task.handler_factory,
            )
        self._tasks[task_id] = task
        await self.job_store.save_scheduled_task(
            {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "enabled": task.enabled,
                "cron": task.cron,
            }
        )
        # Restart scheduler if running to pick up changes
        if self.is_running():
            self.stop()
            self.start()

    async def run_task_now(self, task_id: str) -> dict:
        if task_id not in self._tasks:
            return {"success": False, "message": f"Unknown task: {task_id}"}
        task = self._tasks[task_id]
        handler = task.handler_factory()
        try:
            result = await handler.run()
            return {"success": result.get("success", True), "message": result.get("message", "OK")}
        except Exception as e:
            logger.error("Manual run of %s failed: %s", task_id, e)
            return {"success": False, "message": str(e)}

    def _make_job_wrapper(self, task: ScheduledTask) -> Callable:
        async def wrapper() -> None:
            logger.info("Scheduled task %s triggered at %s", task.id, datetime.now().isoformat())
            handler = task.handler_factory()
            try:
                await handler.run()
            except Exception as e:
                logger.error("Scheduled task %s failed: %s", task.id, e)

        return wrapper
