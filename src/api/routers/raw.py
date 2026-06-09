from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import AppServices, get_services
from src.knowledge.raw_auto_collector import RawAutoCollector
from src.knowledge.raw_models import (
    DailyTradeLogRequest,
    RawMetadataUpdateRequest,
    RawSourceCreateRequest,
    RawSourceUpdateRequest,
)
from src.knowledge.raw_renderers import render_daily_trade_log
from src.portfolio.trade_apply import TradeApplyService

router = APIRouter(prefix="/raw", tags=["raw"])


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail="source not found")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/sources")
async def list_sources(
    source_kind: str | None = None,
    symbol: str | None = None,
    trade_date: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    services: AppServices = Depends(get_services),
):
    return await services.raw_store.list_sources(
        source_kind=source_kind,
        symbol=symbol,
        trade_date=trade_date,
        limit=limit,
        offset=offset,
    )


@router.post("/sources")
async def add_source(
    body: RawSourceCreateRequest,
    services: AppServices = Depends(get_services),
):
    try:
        if body.source_kind == "manual_source" and body.origin != "user":
            raise ValueError("manual_source origin must be user")
        if body.source_kind != "manual_source" and body.origin == "user":
            # Users should use manual_source for pasted material. daily_trade_log has its own endpoint.
            allowed_user_kinds = {"daily_trade_log"}
            if body.source_kind not in allowed_user_kinds:
                raise ValueError("user-created materials must use source_kind=manual_source")
        return await services.raw_store.add_source(
            source_kind=body.source_kind,
            origin=body.origin,
            title=body.title,
            markdown=body.markdown,
            metadata=body.metadata,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/sources/{source_id}")
async def read_source(source_id: str, services: AppServices = Depends(get_services)):
    try:
        return await services.raw_store.read_source(source_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/sources/{source_id}/content")
async def read_source_content(source_id: str, services: AppServices = Depends(get_services)):
    try:
        source = await services.raw_store.read_source(source_id)
        return {"source_id": source_id, "content": source["markdown"]}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.put("/sources/{source_id}")
async def update_source(
    source_id: str,
    body: RawSourceUpdateRequest,
    services: AppServices = Depends(get_services),
):
    try:
        result = await services.raw_store.update_source(
            source_id,
            title=body.title,
            markdown=body.markdown,
            metadata=body.metadata,
        )
        return result
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/sources/{source_id}/metadata")
async def update_metadata(
    source_id: str,
    body: RawMetadataUpdateRequest,
    services: AppServices = Depends(get_services),
):
    try:
        return await services.raw_store.update_metadata(
            source_id,
            tags=body.tags,
            metadata=body.metadata,
        )
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/sources/{source_id}/verify")
async def verify_source(source_id: str, services: AppServices = Depends(get_services)):
    try:
        ok = await services.raw_store.verify_source(source_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=409, detail="sha256_mismatch")
    return {"source_id": source_id, "ok": True}


@router.post("/collect/holding/{symbol}")
async def collect_holding(
    symbol: str,
    limit: int = Query(10, ge=1, le=50),
    services: AppServices = Depends(get_services),
):
    collector = RawAutoCollector(services.collector, services.raw_store, services.portfolio)
    return await collector.collect_holding(symbol, limit=limit)


@router.post("/collect/portfolio")
async def collect_portfolio(
    limit_per_symbol: int = Query(10, ge=1, le=50),
    services: AppServices = Depends(get_services),
):
    collector = RawAutoCollector(services.collector, services.raw_store, services.portfolio)
    return await collector.collect_portfolio(limit_per_symbol=limit_per_symbol)


@router.get("/trade-log")
async def get_trade_log(
    date: str,
    services: AppServices = Depends(get_services),
):
    latest = await services.raw_store.latest_for_trade_date("daily_trade_log", date)
    versions = await services.raw_store.versions_for_trade_date("daily_trade_log", date)
    if not latest:
        return {"trade_date": date, "source": None, "markdown": "", "versions": []}
    source = await services.raw_store.read_source(latest["source_id"])
    return {
        "trade_date": date,
        "source": source,
        "markdown": source["markdown"],
        "versions": versions,
    }


@router.post("/trade-log")
async def save_trade_log(
    body: DailyTradeLogRequest,
    services: AppServices = Depends(get_services),
):
    try:
        entries = [item.model_dump() for item in body.entries]
        overrides = [item.model_dump() for item in body.position_overrides]

        trade_service = TradeApplyService(services.portfolio, services.settings)
        audit = await trade_service.apply_daily_trade_log(
            body.trade_date,
            entries,
            overrides,
        )
        entries = audit.get("entries", entries)
        previous = await services.raw_store.latest_for_trade_date("daily_trade_log", body.trade_date)
        symbols = sorted({entry["symbol"] for entry in entries if entry.get("symbol")})
        markdown = render_daily_trade_log(
            body.trade_date,
            entries,
            notes=body.notes,
            audit=audit,
        )
        source = await services.raw_store.add_source(
            source_kind="daily_trade_log",
            origin="user",
            title=f"{body.trade_date} 每日操作记录",
            markdown=markdown,
            metadata={
                "trade_date": body.trade_date,
                "symbols": symbols,
                "tags": ["trade_log", f"date/{body.trade_date}"] + [f"stock/{s}" for s in symbols],
                "supersedes_source_id": previous["source_id"] if previous else "",
                "entries": entries,
                "position_overrides": overrides,
                "trade_ids": audit.get("trade_ids", []),
            },
        )
        await trade_service.attach_raw_source(audit.get("trade_ids", []), source["source_id"])

        linked_analysis = {
            entry.get("linked_analysis_run_id", "")
            for entry in entries
            if entry.get("linked_analysis_run_id")
        }
        for run_id in linked_analysis:
            await services.raw_store.add_link(source["source_id"], run_id, "analysis_run")
        for entry in entries:
            for linked_source_id in entry.get("linked_source_ids") or []:
                await services.raw_store.add_link(source["source_id"], linked_source_id, "supporting_source")

        return {"source": source, "audit": audit}
    except Exception as exc:
        raise _http_error(exc) from exc
