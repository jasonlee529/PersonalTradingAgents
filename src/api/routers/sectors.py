import asyncio
import dataclasses
import json
import logging
import hashlib
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import get_services, AppServices
from src.api.models import AnalysisRequest, DiscoverStatusResponse, DiscoverPhaseItem
from src.data.cache import DataCache
from src.agents.sector_discovery.coordinator import Coordinator
from src.agents.sector_discovery.models import DirectionContext
from src.data.collector import DataCollector
from src.knowledge.raw_store import RawStore
from src.utils.trading_dates import normalize_trade_date

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sectors", tags=["sectors"])


class SectorDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_code: Optional[str] = None

# In-memory store for discovery job progress (short-lived, no persistence needed)
_discovery_jobs: dict[str, dict] = {}

_DISCOVERY_PHASES = [
    ("scout", "方向发现"),
    ("validate", "多维验证"),
    ("compare", "排序筛选"),
    ("deep_dive", "深度分析"),
    ("report", "生成报告"),
]


def _serialize_context(context: DirectionContext) -> dict:
    """Serialize DirectionContext to JSON-serializable dict for frontend."""
    return {
        "date": context.date,
        "market_overview": context.market_overview,
        "news_context": context.news_context,
        "candidate_directions": [
            dataclasses.asdict(c) for c in context.candidate_directions
        ],
        "validation_results": [
            dataclasses.asdict(r) for r in context.validation_results
        ],
        "selected_directions": [
            dataclasses.asdict(s) for s in context.selected_directions
        ],
        "deep_analysis": {
            name: dataclasses.asdict(d) for name, d in context.deep_analysis.items()
        },
        "execution_log": [
            dataclasses.asdict(e) for e in context.execution_log
        ],
    }


def _make_discovery_status(job_id: str) -> DiscoverStatusResponse:
    job = _discovery_jobs.get(job_id, {})
    phases = job.get("phases", [])
    status = job.get("status", "pending")
    # Calculate progress based on completed phases
    total = len(_DISCOVERY_PHASES)
    completed = sum(1 for p in phases if p.get("status") in ("success", "failure", "timeout", "fallback"))
    progress_pct = min(100, int((completed / total) * 100)) if total else 0
    if status == "running" and completed == total:
        progress_pct = 99
    if status in ("completed", "failed"):
        progress_pct = 100
    return DiscoverStatusResponse(
        job_id=job_id,
        status=status,
        progress_pct=progress_pct,
        phase=job.get("current_phase", ""),
        message=job.get("message", ""),
        error=job.get("error", ""),
        phases=[
            DiscoverPhaseItem(
                phase=p["phase"],
                label=p.get("label", p["phase"]),
                status=p.get("status", "pending"),
                duration_ms=p.get("duration_ms", 0),
                message=p.get("message", ""),
            )
            for p in phases
        ],
        result_summary=job.get("result_summary", ""),
        created_at=job.get("created_at", ""),
        completed_at=job.get("completed_at"),
    )


def _is_valid_direction_analysis(analysis_data: dict) -> bool:
    if not analysis_data:
        return True
    market_overview = analysis_data.get("market_overview") or {}
    stats = market_overview.get("statistics") or {}
    if not stats:
        return False
    breadth = sum(int(stats.get(k) or 0) for k in ("up_count", "down_count", "flat_count"))
    return breadth >= 1000


@router.get("/today")
async def get_today_directions(
    date: Optional[str] = None,
    limit: int = 10,
    services: AppServices = Depends(get_services),
):
    """Get today's (or specified date's) sector discovery direction report with full structured data.

    Args:
        date: Optional date string (YYYY-MM-DD). Defaults to latest.
        limit: Max number of reports to return.
    """
    requested_date = date or normalize_trade_date(datetime.now().strftime("%Y-%m-%d"))
    logger.info("API GET /sectors/today date=%s limit=%d", requested_date, limit)
    try:
        results = []
        # Explicit date means exact lookup; default means latest available report.
        trade_date_filter = requested_date if date else None
        entries = await services.raw_store.list_sources(
            source_kind="daily_direction",
            trade_date=trade_date_filter,
            limit=limit,
        )
        response_date = entries[0].get("trade_date", requested_date) if entries else requested_date
        valid_results = []
        legacy_results = []
        for entry in entries:
            try:
                source = await services.raw_store.read_source(entry["source_id"])
            except FileNotFoundError:
                logger.warning("Source file missing for %s, skipping", entry["source_id"])
                continue
            stable_id = int(hashlib.sha256(entry["source_id"].encode("utf-8")).hexdigest()[:8], 16)
            meta = entry.get("metadata") or {}
            analysis_data = meta.get("analysis_data") or {}
            report = {
                "id": stable_id,
                "source_id": entry["source_id"],
                "date": entry.get("trade_date", ""),
                "title": entry["title"],
                "summary": meta.get("summary", ""),
                "tags": entry.get("tags", []),
                "content": source.get("markdown", ""),
                "created_at": entry.get("created_at", ""),
                "sectors": analysis_data.get("selected_directions", []),
                "validation_results": analysis_data.get("validation_results", []),
                "deep_analysis": analysis_data.get("deep_analysis", {}),
                "execution_log": analysis_data.get("execution_log", []),
                "candidate_count": len(analysis_data.get("candidate_directions", [])),
            }
            if not _is_valid_direction_analysis(analysis_data):
                logger.warning(
                    "Daily direction report %s has legacy or incomplete market statistics",
                    entry["source_id"],
                )
                legacy_results.append(report)
                continue
            valid_results.append(report)

        results = valid_results + legacy_results

        logger.info("API GET /sectors/today returned %d reports", len(results))
        if results:
            response_date = results[0].get("date") or response_date
        return {"date": response_date, "reports": results}
    except Exception as e:
        logger.error("Failed to get today directions: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{stock}/analyze")
async def analyze_stock(
    stock: str,
    request: Optional[AnalysisRequest] = None,
    services: AppServices = Depends(get_services),
):
    """Trigger a full TradingAgents analysis for a specific stock.

    This is the bridge from Sector Discovery (direction recommendation)
    to TradingAgents (deep analysis).
    """
    try:
        from src.agents.trading_agents_wrapper import TradingAgentsWrapper

        settings = services.settings
        cache = DataCache(settings)
        await cache.init_db()

        wrapper = TradingAgentsWrapper(settings, cache=cache)

        result = await wrapper.analyze(stock)
        return {
            "symbol": stock,
            "status": "completed",
            "result": result,
        }
    except Exception as e:
        logger.error("Failed to analyze %s: %s", stock, e)
        raise HTTPException(status_code=500, detail=str(e))


async def _run_discovery_background(
    job_id: str,
    settings,
    board_code: Optional[str],
):
    # settings type: src.config.Settings (avoid circular import at module level)
    """Background task for sector discovery with progress tracking."""
    job = _discovery_jobs[job_id]
    job["status"] = "running"
    job["current_phase"] = "初始化"
    job["message"] = "正在启动方向扫描..."

    def _on_phase_update(phase: str, status: str, message: str = "", duration_ms: int = 0):
        job["current_phase"] = phase
        for p in job["phases"]:
            if p["phase"] == phase:
                p["status"] = status
                p["message"] = message
                p["duration_ms"] = duration_ms
                break
        if status == "running":
            job["message"] = message or f"正在执行: {phase}..."
        logger.debug("Discovery job %s phase %s: %s", job_id, phase, status)

    try:
        cache = DataCache(settings)
        await cache.init_db()
        collector = DataCollector(settings, cache)
        now_str = datetime.now().strftime("%Y-%m-%d")
        original_date = now_str
        trade_date = normalize_trade_date(now_str)
        context = DirectionContext(
            date=trade_date,
            original_date=original_date,
            market_overview={},
            news_context="",
        )
        coordinator = Coordinator(settings, cache, collector)
        report = await coordinator.run(context=context, on_phase=_on_phase_update)

        # Persist report to raw_store so /sectors/today can serve it
        try:
            raw_store = RawStore(settings)
            await raw_store.init_db()
            tags = list({t for s in report.sectors for t in s.tags})
            # Serialize full analysis context for frontend structured display
            analysis_data = _serialize_context(context)
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
                    "analysis_data": analysis_data,
                    "run_id": job_id,
                },
            )
            logger.info("Discovery job %s persisted to raw_store", job_id)

            # Push notification if enabled
            if getattr(settings, "daily_direction_notification_enabled", False):
                try:
                    from src.services.notification import NotificationService
                    notifier = NotificationService(settings)
                    rel_path = result.get("content_path", "")
                    if rel_path:
                        push_result = await notifier.push_raw(
                            rel_path,
                            route_type="report",
                        )
                        if push_result.success:
                            logger.info(
                                "Discovery job %s notification pushed to %d channels",
                                job_id, len(push_result.channel_results),
                            )
                        else:
                            logger.warning(
                                "Discovery job %s notification push failed: %s",
                                job_id, push_result.message,
                            )
                except Exception as notify_err:
                    logger.error("Discovery job %s notification push error: %s", job_id, notify_err)

        except Exception as persist_err:
            logger.warning("Discovery job %s failed to persist: %s", job_id, persist_err)
            job["error"] = f"Persist failed: {persist_err}"

        job["status"] = "completed"
        job["message"] = f"扫描完成，发现 {len(report.sectors)} 个方向"
        job["result_summary"] = report.summary
        job["completed_at"] = datetime.now().isoformat()
        logger.info(
            "Sector discovery job %s completed: date=%s sectors=%d",
            job_id, report.date, len(report.sectors),
        )
    except Exception as e:
        logger.error("Sector discovery job %s failed: %s", job_id, e)
        job["status"] = "failed"
        job["error"] = str(e)
        job["message"] = f"扫描失败: {e}"
        job["completed_at"] = datetime.now().isoformat()


@router.post("/discover")
async def run_sector_discovery(
    body: Optional[SectorDiscoveryRequest] = None,
    services: AppServices = Depends(get_services),
):
    """Manually trigger a sector discovery scan. Returns job_id immediately."""
    board_code = body.board_code if body else None
    logger.info("API POST /sectors/discover board_code=%s", board_code or "all")
    job_id = str(uuid.uuid4())[:8]
    now = datetime.now().isoformat()
    _discovery_jobs[job_id] = {
        "status": "pending",
        "current_phase": "",
        "message": "等待开始...",
        "error": "",
        "result_summary": "",
        "created_at": now,
        "completed_at": None,
        "phases": [
            {"phase": key, "label": label, "status": "pending", "message": "", "duration_ms": 0}
            for key, label in _DISCOVERY_PHASES
        ],
    }
    asyncio.create_task(_run_discovery_background(job_id, services.settings, board_code))
    return {"job_id": job_id, "status": "pending", "message": "方向扫描已启动"}


@router.get("/discover/status/{job_id}", response_model=DiscoverStatusResponse)
async def get_discovery_status(job_id: str):
    """Get the status of a running or completed sector discovery job."""
    if job_id not in _discovery_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _make_discovery_status(job_id)
