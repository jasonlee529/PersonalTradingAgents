from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies import AppServices, get_services
from src.knowledge.wiki_models import WIKI_RUNNING_SOURCE_STATUSES
from src.knowledge.wiki_lint import WikiLintService

router = APIRouter(prefix="/wiki", tags=["wiki"])


class WikiIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force: bool = False


class WikiBatchIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ids: list[str]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail="not found")
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def _normalise_claim_record(row: dict) -> dict:
    return {
        **row,
        "source_ids": _json_list(row.get("source_ids_json")),
        "page_ids": _json_list(row.get("page_ids_json")),
        "contradicts": _json_list(row.get("contradicts_json")),
    }


def _is_ingestable_source_status(status: str) -> bool:
    return status in {"pending", "failed", "needs_reprocess", *WIKI_RUNNING_SOURCE_STATUSES}


# Pages
@router.get("/pages")
async def list_pages(
    page_type: str | None = None,
    symbol: str | None = None,
    topic: str | None = None,
    trade_date: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    services: AppServices = Depends(get_services),
):
    return await services.wiki_store.list_pages(
        page_type=page_type,
        symbol=symbol,
        topic=topic,
        trade_date=trade_date,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/pages/{page_id}")
async def get_page(page_id: str, services: AppServices = Depends(get_services)):
    try:
        return await services.wiki_store.read_page(page_id)
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/pages/{page_id}/content")
async def get_page_content(page_id: str, services: AppServices = Depends(get_services)):
    try:
        page = await services.wiki_store.read_page(page_id)
        return {"page_id": page_id, "content": page["markdown"]}
    except Exception as exc:
        raise _http_error(exc) from exc


@router.get("/pages/by-slug/{slug}")
async def get_page_by_slug(slug: str, services: AppServices = Depends(get_services)):
    page = await services.wiki_store.get_page_by_slug(slug)
    if not page:
        raise HTTPException(status_code=404, detail="page not found")
    return page


@router.post("/pages/{page_id}/verify")
async def verify_page(page_id: str, services: AppServices = Depends(get_services)):
    try:
        ok = await services.wiki_store.verify_page(page_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    if not ok:
        raise HTTPException(status_code=409, detail="sha256_mismatch")
    return {"page_id": page_id, "ok": True}


# Pending sources
@router.get("/sources/pending")
async def list_pending_sources(
    limit: int = Query(100, ge=1, le=200),
    services: AppServices = Depends(get_services),
):
    raw_sources = await services.raw_store.list_sources(limit=1000)
    states = await services.wiki_store.list_source_states(limit=1000)
    state_map = {s["source_id"]: s for s in states}

    pending = []
    for rs in raw_sources:
        sid = rs["source_id"]
        st = state_map.get(sid)
        status = st.get("wiki_status", "pending") if st else "pending"
        if not st or _is_ingestable_source_status(status):
            pending.append({
                **rs,
                "wiki_status": status,
                "latest_ingest_run_id": st.get("latest_ingest_run_id", "") if st else "",
                "wiki_error": st.get("error", "") if st else "",
                "wiki_page_ids": st.get("page_ids", []) if st else [],
            })

    return pending[:limit]


# Ingest
@router.post("/ingest/source/{source_id}")
async def ingest_source(
    source_id: str,
    body: WikiIngestRequest,
    services: AppServices = Depends(get_services),
):
    try:
        return await services.wiki_ingest_queue.enqueue_source(source_id, force=body.force)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/ingest/analysis-run/{run_id}")
async def ingest_analysis_run(
    run_id: str,
    body: WikiIngestRequest,
    services: AppServices = Depends(get_services),
):
    try:
        return await services.wiki_ingest_queue.enqueue_analysis_run(run_id, force=body.force)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise _http_error(exc) from exc


@router.post("/ingest/batch")
async def ingest_batch(
    body: WikiBatchIngestRequest,
    services: AppServices = Depends(get_services),
):
    return await services.wiki_ingest_queue.enqueue_batch(
        body.source_ids,
    )


@router.get("/ingest/runs")
async def list_ingest_runs(
    limit: int = Query(50, ge=1, le=200),
    services: AppServices = Depends(get_services),
):
    async with __import__("aiosqlite").connect(services.wiki_store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM wiki_ingest_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


@router.get("/ingest/runs/{run_id}")
async def get_ingest_run(run_id: str, services: AppServices = Depends(get_services)):
    async with __import__("aiosqlite").connect(services.wiki_store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM wiki_ingest_runs WHERE run_id = ?", (run_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="run not found")
            return dict(row)


# Claims
@router.get("/claims")
async def list_claims(
    subject_type: str | None = None,
    subject_id: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    services: AppServices = Depends(get_services),
):
    clauses = []
    params = []
    if subject_type:
        clauses.append("subject_type = ?")
        params.append(subject_type)
    if subject_id:
        clauses.append("subject_id = ?")
        params.append(subject_id)
    if claim_type:
        clauses.append("claim_type = ?")
        params.append(claim_type)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM wiki_claims{where} ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    async with __import__("aiosqlite").connect(services.wiki_store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [_normalise_claim_record(dict(r)) for r in rows]


@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str, services: AppServices = Depends(get_services)):
    async with __import__("aiosqlite").connect(services.wiki_store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM wiki_claims WHERE claim_id = ?", (claim_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="claim not found")
            return _normalise_claim_record(dict(row))


# Rebuild index
@router.post("/rebuild-index")
async def rebuild_index(services: AppServices = Depends(get_services)):
    return await services.wiki_store.rebuild_index()


# Lint
@router.post("/lint")
async def run_lint(services: AppServices = Depends(get_services)):
    lint_service = WikiLintService(
        services.wiki_store,
        raw_db_path=services.settings.raw_knowledge_db_path,
    )
    return await lint_service.run()


@router.get("/lint/latest")
async def get_latest_lint(services: AppServices = Depends(get_services)):
    lint_service = WikiLintService(
        services.wiki_store,
        raw_db_path=services.settings.raw_knowledge_db_path,
    )
    result = await lint_service.get_latest()
    if not result:
        raise HTTPException(status_code=404, detail="no lint result yet")
    return result


class WikiSaveQueryRequest(BaseModel):
    question: str
    answer_markdown: str
    cited_page_ids: list[str] = Field(default_factory=list)
    cited_source_ids: list[str] = Field(default_factory=list)


@router.post("/query/save")
async def save_query(
    body: WikiSaveQueryRequest,
    services: AppServices = Depends(get_services),
):
    import hashlib
    from datetime import datetime

    now = datetime.now().astimezone().isoformat(timespec="microseconds")
    safe_q = hashlib.sha256(body.question.encode("utf-8")).hexdigest()[:8]
    page_id = f"query:{now[:10]}:{safe_q}"
    slug = f"queries/{now[:10]}_{safe_q}"
    title = f"Q: {body.question[:60]}"

    markdown = f"# {body.question}\n\n{body.answer_markdown}\n\n"
    if body.cited_page_ids:
        markdown += "## 引用页面\n\n"
        for pid in body.cited_page_ids:
            markdown += f"- [[{pid}]]\n"
    if body.cited_source_ids:
        markdown += "\n## 引用来源\n\n"
        for sid in body.cited_source_ids:
            markdown += f"- `{sid}`\n"

    page = await services.wiki_store.upsert_page(
        page_id=page_id,
        page_type="saved_query",
        title=title,
        slug=slug,
        markdown=markdown,
        metadata={
            "question": body.question,
            "cited_page_ids": body.cited_page_ids,
            "cited_source_ids": body.cited_source_ids,
            "tags": ["saved_query"],
            "source_ids": body.cited_source_ids,
        },
    )

    for sid in body.cited_source_ids:
        await services.wiki_store.link_page_source(page_id, sid, source_role="context")

    log_entry = f"## [{now}] saved_query | {page_id} | {body.question[:40]}\n\n- page_id: {page_id}\n- cited_pages: {len(body.cited_page_ids)}\n- cited_sources: {len(body.cited_source_ids)}"
    await services.wiki_store.append_log(log_entry)
    await services.wiki_store.rebuild_index()

    return {
        "page_id": page_id,
        "page_type": "saved_query",
        "title": title,
        "slug": slug,
    }
