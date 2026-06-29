from __future__ import annotations

import hashlib
from datetime import datetime

from src.config import Settings
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore
from src.knowledge.wiki_schema import WikiSchema
from src.knowledge.wiki_planner import create_wiki_planner
from src.knowledge.wiki_models import (
    WIKI_RUNNING_SOURCE_STATUSES,
    WikiUpdatePlan,
    validate_wiki_update_plan,
)


def _stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class WikiIngestor:
    def __init__(
        self,
        settings: Settings,
        raw_store: RawStore,
        wiki_store: WikiStore,
        schema: WikiSchema | None = None,
        planner: DeterministicWikiPlanner | None = None,
    ):
        self.settings = settings
        self.raw_store = raw_store
        self.wiki_store = wiki_store
        self.schema = schema or WikiSchema(settings)
        self.planner = planner or create_wiki_planner(settings, wiki_store=wiki_store)

    async def ingest_source(
        self,
        source_id: str,
        *,
        force: bool = False,
        run_id: str | None = None,
    ) -> dict:
        # 1. Read raw source
        try:
            source = await self.raw_store.read_source(source_id)
        except FileNotFoundError:
            return self._error_run("source", source_id, f"Raw source not found: {source_id}")

        rid = run_id or self._new_run_id(source_id)

        # 2. Verify hash
        if not await self.raw_store.verify_source(source_id):
            error_msg = "Raw source hash mismatch"
            await self._create_ingest_run(
                rid,
                "source",
                source_id,
                source.get("source_kind", ""),
                "apply",
                status="failed",
            )
            await self._mark_source_failed(source, rid, error_msg)
            await self._fail_ingest_run(rid, error_msg)
            return {
                "run_id": rid,
                "status": "failed",
                "source_ids": [source_id],
                "pages_touched": [],
                "claims_touched": [],
                "warnings": [error_msg],
            }

        # 3. Check source state
        state = await self.wiki_store.get_source_state(source_id)
        if (
            state
            and state.get("wiki_status") in WIKI_RUNNING_SOURCE_STATUSES
            and state.get("latest_ingest_run_id")
            and state.get("latest_ingest_run_id") != rid
        ):
            return {
                "run_id": state.get("latest_ingest_run_id", ""),
                "status": state.get("wiki_status", "applying"),
                "source_ids": [source_id],
                "pages_touched": state.get("page_ids", []),
                "claims_touched": [],
                "warnings": ["Source already queued or running"],
            }
        if state and state.get("wiki_status") == "processed" and not force:
            return {
                "run_id": "",
                "status": "skipped",
                "source_ids": [source_id],
                "pages_touched": state.get("page_ids", []),
                "claims_touched": [],
                "warnings": ["Source already processed"],
            }

        pages_touched: list[dict] = []
        claims_touched: list[str] = []

        try:
            # 4. Enter planning state before expensive work.
            await self._create_ingest_run(rid, "source", source_id, source.get("source_kind", ""), "apply", status="planning")
            await self._mark_source_running(source, rid, "planning")

            # 5. Find related pages
            related_pages = await self._find_related_pages(source)

            # 6. Read schema
            schema_text = await self.schema.read_schema()

            # 7. Planner generates plan
            plan = await self.planner.plan_source_ingest(
                source=source,
                related_pages=related_pages,
                schema_text=schema_text,
            )

            # 8. Validate plan
            validation = self._validate_plan(plan)
            if validation["errors"]:
                error_msg = "; ".join(validation["errors"])
                await self._fail_ingest_run(rid, error_msg)
                await self._mark_source_failed(source, rid, error_msg)
                return {
                    "run_id": rid,
                    "status": "failed",
                    "source_ids": [source_id],
                    "pages_touched": [],
                    "claims_touched": [],
                    "warnings": [error_msg],
                }

            await self.wiki_store.save_plan_to_run(rid, plan.model_dump())
            await self._update_ingest_run_status(rid, "applying")
            await self._mark_source_running(source, rid, "applying")

            # Upsert pages_to_create
            for page in plan.pages_to_create:
                result = await self.wiki_store.upsert_page(
                    page_id=page.page_id,
                    page_type=page.page_type,
                    title=page.title,
                    slug=page.slug,
                    markdown=page.markdown,
                    metadata=page.metadata,
                )
                pages_touched.append({
                    "page_id": result["page_id"],
                    "title": result["title"],
                    "page_type": result["page_type"],
                    "slug": result.get("slug", ""),
                })

            # Patch sections
            created_page_ids = {p.page_id for p in plan.pages_to_create}
            patch_failures: list[str] = []
            patch_successes = 0
            for patch in plan.page_patches:
                try:
                    result = await self.wiki_store.patch_section(
                        patch.page_id,
                        section_id=patch.section_id,
                        markdown=patch.markdown,
                        mode=patch.mode,
                    )
                    pages_touched.append({
                        "page_id": result["page_id"],
                        "title": result["title"],
                        "page_type": result["page_type"],
                        "slug": result.get("slug", ""),
                    })
                    patch_successes += 1
                except ValueError as e:
                    warning = f"Patch failed for {patch.page_id}/{patch.section_id}: {e}"
                    plan.warnings.append(warning)
                    patch_failures.append(warning)
                    # A required patch (target page was just created by this plan) is critical
                    if patch.page_id in created_page_ids:
                        error_msg = f"Required patch failed: {warning}"
                        await self._fail_ingest_run(rid, error_msg)
                        await self._mark_source_failed(source, rid, error_msg)
                        return {
                            "run_id": rid,
                            "status": "failed",
                            "source_ids": [source_id],
                            "pages_touched": pages_touched,
                            "claims_touched": claims_touched,
                            "warnings": plan.warnings,
                        }

            # If all patches failed and there were patches intended, fail the ingest
            if plan.page_patches and patch_successes == 0:
                error_msg = "All intended page patches failed: " + "; ".join(patch_failures)
                await self._fail_ingest_run(rid, error_msg)
                await self._mark_source_failed(source, rid, error_msg)
                return {
                    "run_id": rid,
                    "status": "failed",
                    "source_ids": [source_id],
                    "pages_touched": pages_touched,
                    "claims_touched": claims_touched,
                    "warnings": plan.warnings,
                }

            # Upsert claims
            for claim in plan.claims:
                result = await self.wiki_store.upsert_claim(claim.model_dump())
                claims_touched.append(result["claim_id"])

            # Link page sources
            for page in plan.pages_to_create:
                for sid in page.metadata.get("source_ids", []):
                    await self.wiki_store.link_page_source(page.page_id, sid, source_role="generated_from")

            # Update source state
            page_ids = list({p["page_id"] for p in pages_touched})
            await self.wiki_store.upsert_source_state(
                source_id=source_id,
                source_kind=source.get("source_kind", ""),
                raw_content_sha256=source.get("content_sha256", ""),
                wiki_status="processed",
                latest_ingest_run_id=rid,
                page_ids=page_ids,
            )

            # Append log
            await self.wiki_store.append_log(plan.log_entry)

            # Rebuild index
            await self.wiki_store.rebuild_index()

            await self._complete_ingest_run(rid, pages_touched, claims_touched)

            return {
                "run_id": rid,
                "status": "completed",
                "source_ids": [source_id],
                "pages_touched": pages_touched,
                "claims_touched": claims_touched,
                "warnings": plan.warnings,
            }

        except Exception as e:
            await self._fail_ingest_run(rid, str(e))
            await self._mark_source_failed(source, rid, str(e))
            raise

    async def ingest_analysis_run(
        self,
        run_id: str,
        *,
        force: bool = False,
        ingest_run_id: str | None = None,
    ) -> dict:
        # Query raw sources with source_kind=stock_analysis and matching run_id
        all_sources = await self.raw_store.list_sources(source_kind="stock_analysis", limit=200)
        sources = [
            s for s in all_sources
            if s.get("metadata", {}).get("run_id") == run_id
        ]

        if not sources:
            return self._error_run("analysis_run", "", f"No stock_analysis sources found for run_id: {run_id}")

        rid = ingest_run_id or self._new_run_id(run_id)

        for source in sources:
            state = await self.wiki_store.get_source_state(source["source_id"])
            if (
                state
                and state.get("wiki_status") in WIKI_RUNNING_SOURCE_STATUSES
                and state.get("latest_ingest_run_id")
                and state.get("latest_ingest_run_id") != rid
            ):
                return {
                    "run_id": state.get("latest_ingest_run_id", ""),
                    "status": state.get("wiki_status", "applying"),
                    "source_ids": [s["source_id"] for s in sources],
                    "pages_touched": state.get("page_ids", []),
                    "claims_touched": [],
                    "warnings": ["Analysis run already queued or running"],
                }

        # Check if all already processed
        if not force:
            all_processed = True
            for s in sources:
                state = await self.wiki_store.get_source_state(s["source_id"])
                if not state or state.get("wiki_status") != "processed":
                    all_processed = False
                    break
            if all_processed:
                return {
                    "run_id": "",
                    "status": "skipped",
                    "source_ids": [s["source_id"] for s in sources],
                    "pages_touched": [],
                    "claims_touched": [],
                    "warnings": ["All sources already processed"],
                }

        pages_touched: list[dict] = []
        claims_touched: list[str] = []

        try:
            await self._create_ingest_run(
                rid,
                "analysis_run",
                "",
                sources[0].get("source_kind", ""),
                "apply",
                raw_run_id=run_id,
                status="planning",
            )
            for source in sources:
                await self._mark_source_running(source, rid, "planning")

            # Find related pages
            symbol = sources[0].get("symbol", "")
            related_pages = await self.wiki_store.list_pages(symbol=symbol, limit=50) if symbol else []

            # Read schema
            schema_text = await self.schema.read_schema()

            plan = await self.planner.plan_analysis_run_ingest(
                sources=sources,
                related_pages=related_pages,
                schema_text=schema_text,
            )

            validation = self._validate_plan(plan)
            if validation["errors"]:
                error_msg = "; ".join(validation["errors"])
                await self._fail_ingest_run(rid, error_msg)
                for source in sources:
                    await self._mark_source_failed(source, rid, error_msg)
                return {
                    "run_id": rid,
                    "status": "failed",
                    "source_ids": [s["source_id"] for s in sources],
                    "pages_touched": [],
                    "claims_touched": [],
                    "warnings": [error_msg],
                }

            await self.wiki_store.save_plan_to_run(rid, plan.model_dump())
            await self._update_ingest_run_status(rid, "applying")
            for source in sources:
                await self._mark_source_running(source, rid, "applying")

            for page in plan.pages_to_create:
                result = await self.wiki_store.upsert_page(
                    page_id=page.page_id,
                    page_type=page.page_type,
                    title=page.title,
                    slug=page.slug,
                    markdown=page.markdown,
                    metadata=page.metadata,
                )
                pages_touched.append({
                    "page_id": result["page_id"],
                    "title": result["title"],
                    "page_type": result["page_type"],
                    "slug": result.get("slug", ""),
                })

            created_page_ids = {p.page_id for p in plan.pages_to_create}
            patch_failures: list[str] = []
            patch_successes = 0
            for patch in plan.page_patches:
                try:
                    result = await self.wiki_store.patch_section(
                        patch.page_id,
                        section_id=patch.section_id,
                        markdown=patch.markdown,
                        mode=patch.mode,
                    )
                    pages_touched.append({
                        "page_id": result["page_id"],
                        "title": result["title"],
                        "page_type": result["page_type"],
                        "slug": result.get("slug", ""),
                    })
                    patch_successes += 1
                except ValueError as e:
                    warning = f"Patch failed for {patch.page_id}/{patch.section_id}: {e}"
                    plan.warnings.append(warning)
                    patch_failures.append(warning)
                    if patch.page_id in created_page_ids:
                        error_msg = f"Required patch failed: {warning}"
                        await self._fail_ingest_run(rid, error_msg)
                        for s in sources:
                            await self._mark_source_failed(s, rid, error_msg)
                        return {
                            "run_id": rid,
                            "status": "failed",
                            "source_ids": [s["source_id"] for s in sources],
                            "pages_touched": pages_touched,
                            "claims_touched": claims_touched,
                            "warnings": plan.warnings,
                        }

            if plan.page_patches and patch_successes == 0:
                error_msg = "All intended page patches failed: " + "; ".join(patch_failures)
                await self._fail_ingest_run(rid, error_msg)
                for s in sources:
                    await self._mark_source_failed(s, rid, error_msg)
                return {
                    "run_id": rid,
                    "status": "failed",
                    "source_ids": [s["source_id"] for s in sources],
                    "pages_touched": pages_touched,
                    "claims_touched": claims_touched,
                    "warnings": plan.warnings,
                }

            for claim in plan.claims:
                result = await self.wiki_store.upsert_claim(claim.model_dump())
                claims_touched.append(result["claim_id"])

            for page in plan.pages_to_create:
                for sid in page.metadata.get("source_ids", []):
                    await self.wiki_store.link_page_source(page.page_id, sid, source_role="generated_from")

            # Mark all sources as processed
            page_ids = list({p["page_id"] for p in pages_touched})
            for s in sources:
                await self.wiki_store.upsert_source_state(
                    source_id=s["source_id"],
                    source_kind=s.get("source_kind", ""),
                    raw_content_sha256=s.get("content_sha256", ""),
                    wiki_status="processed",
                    latest_ingest_run_id=rid,
                    page_ids=page_ids,
                )

            await self.wiki_store.append_log(plan.log_entry)
            await self.wiki_store.rebuild_index()
            await self._complete_ingest_run(rid, pages_touched, claims_touched)

            return {
                "run_id": rid,
                "status": "completed",
                "source_ids": [s["source_id"] for s in sources],
                "pages_touched": pages_touched,
                "claims_touched": claims_touched,
                "warnings": plan.warnings,
            }

        except Exception as e:
            await self._fail_ingest_run(rid, str(e))
            for source in sources:
                await self._mark_source_failed(source, rid, str(e))
            raise

    async def ingest_batch(
        self,
        source_ids: list[str],
        *,
        force: bool = False,
        run_id: str | None = None,
    ) -> dict:
        requested_ids = list(dict.fromkeys(source_ids))[: self.settings.wiki_ingest_batch_size]
        rid = run_id or self._new_run_id("|".join(requested_ids))
        source_errors: list[dict] = []
        sources: list[dict] = []

        for sid in requested_ids:
            try:
                source = await self.raw_store.read_source(sid)
            except FileNotFoundError:
                source_errors.append({"source_id": sid, "status": "failed", "error": "Source not found"})
                continue

            if not await self.raw_store.verify_source(sid):
                error_msg = "Raw source hash mismatch"
                await self._mark_source_failed(source, rid, error_msg)
                source_errors.append({"source_id": sid, "status": "failed", "error": error_msg})
                continue

            state = await self.wiki_store.get_source_state(sid)
            if (
                state
                and state.get("wiki_status") in WIKI_RUNNING_SOURCE_STATUSES
                and state.get("latest_ingest_run_id")
                and state.get("latest_ingest_run_id") != rid
            ):
                source_errors.append({
                    "source_id": sid,
                    "status": state.get("wiki_status", "applying"),
                    "error": "Source already queued or running",
                    "run_id": state.get("latest_ingest_run_id", ""),
                })
                continue
            if state and state.get("wiki_status") == "processed" and not force:
                source_errors.append({
                    "source_id": sid,
                    "status": "skipped",
                    "run_id": state.get("latest_ingest_run_id", ""),
                    "pages_touched": state.get("page_ids", []),
                    "claims_touched": [],
                    "warnings": ["Source already processed"],
                })
                continue
            sources.append(source)

        if not sources:
            return {
                "run_id": rid,
                "status": "failed" if any(r.get("status") == "failed" for r in source_errors) else "skipped",
                "source_ids": [],
                "pages_touched": [],
                "claims_touched": [],
                "warnings": [r.get("error", "") for r in source_errors if r.get("error")],
                "batch_status": "failed" if any(r.get("status") == "failed" for r in source_errors) else "skipped",
                "results": source_errors,
            }

        pages_touched: list[dict] = []
        claims_touched: list[str] = []
        batch_source_ids = [s["source_id"] for s in sources]

        try:
            await self._create_ingest_run(
                rid,
                "batch",
                "",
                "batch",
                "apply",
                status="planning",
            )
            for source in sources:
                await self._mark_source_running(source, rid, "planning")

            related_pages = await self._find_related_pages_for_sources(sources)
            schema_text = await self.schema.read_schema()
            plan = await self.planner.plan_batch_ingest(
                sources=sources,
                related_pages=related_pages,
                schema_text=schema_text,
            )

            errors = validate_wiki_update_plan(plan, valid_source_ids=set(batch_source_ids))
            if errors:
                error_msg = "; ".join(errors)
                await self._fail_ingest_run(rid, error_msg)
                for source in sources:
                    await self._mark_source_failed(source, rid, error_msg)
                return {
                    "run_id": rid,
                    "status": "failed",
                    "source_ids": batch_source_ids,
                    "pages_touched": [],
                    "claims_touched": [],
                    "warnings": [error_msg],
                    "batch_status": "failed",
                    "results": source_errors,
                }

            await self.wiki_store.save_plan_to_run(rid, plan.model_dump())
            await self._update_ingest_run_status(rid, "applying")
            for source in sources:
                await self._mark_source_running(source, rid, "applying")

            created_page_ids = {p.page_id for p in plan.pages_to_create}
            for page in plan.pages_to_create:
                result = await self.wiki_store.upsert_page(
                    page_id=page.page_id,
                    page_type=page.page_type,
                    title=page.title,
                    slug=page.slug,
                    markdown=page.markdown,
                    metadata=page.metadata,
                )
                pages_touched.append({
                    "page_id": result["page_id"],
                    "title": result["title"],
                    "page_type": result["page_type"],
                    "slug": result.get("slug", ""),
                })

            patch_failures: list[str] = []
            patch_successes = 0
            for patch in plan.page_patches:
                try:
                    result = await self.wiki_store.patch_section(
                        patch.page_id,
                        section_id=patch.section_id,
                        markdown=patch.markdown,
                        mode=patch.mode,
                    )
                    pages_touched.append({
                        "page_id": result["page_id"],
                        "title": result["title"],
                        "page_type": result["page_type"],
                        "slug": result.get("slug", ""),
                    })
                    patch_successes += 1
                except ValueError as e:
                    warning = f"Patch failed for {patch.page_id}/{patch.section_id}: {e}"
                    plan.warnings.append(warning)
                    patch_failures.append(warning)
                    if patch.page_id in created_page_ids:
                        error_msg = f"Required patch failed: {warning}"
                        await self._fail_ingest_run(rid, error_msg)
                        for source in sources:
                            await self._mark_source_failed(source, rid, error_msg)
                        return {
                            "run_id": rid,
                            "status": "failed",
                            "source_ids": batch_source_ids,
                            "pages_touched": pages_touched,
                            "claims_touched": claims_touched,
                            "warnings": plan.warnings,
                            "batch_status": "failed",
                            "results": source_errors,
                        }

            if plan.page_patches and patch_successes == 0:
                error_msg = "All intended page patches failed: " + "; ".join(patch_failures)
                await self._fail_ingest_run(rid, error_msg)
                for source in sources:
                    await self._mark_source_failed(source, rid, error_msg)
                return {
                    "run_id": rid,
                    "status": "failed",
                    "source_ids": batch_source_ids,
                    "pages_touched": pages_touched,
                    "claims_touched": claims_touched,
                    "warnings": plan.warnings,
                    "batch_status": "failed",
                    "results": source_errors,
                }

            for claim in plan.claims:
                result = await self.wiki_store.upsert_claim(claim.model_dump())
                claims_touched.append(result["claim_id"])

            for page in plan.pages_to_create:
                for sid in page.metadata.get("source_ids", []):
                    await self.wiki_store.link_page_source(page.page_id, sid, source_role="generated_from")

            page_ids = list({p["page_id"] for p in pages_touched})
            for source in sources:
                await self.wiki_store.upsert_source_state(
                    source_id=source["source_id"],
                    source_kind=source.get("source_kind", ""),
                    raw_content_sha256=source.get("content_sha256", ""),
                    wiki_status="processed",
                    latest_ingest_run_id=rid,
                    page_ids=page_ids,
                )

            if plan.log_entry:
                await self.wiki_store.append_log(plan.log_entry)
            await self.wiki_store.rebuild_index()
            await self._complete_ingest_run(rid, pages_touched, claims_touched)

            result = {
                "run_id": rid,
                "status": "completed",
                "source_ids": batch_source_ids,
                "pages_touched": pages_touched,
                "claims_touched": claims_touched,
                "warnings": plan.warnings,
            }
            return {
                **result,
                "batch_status": "completed",
                "results": [{"source_id": sid, **result} for sid in batch_source_ids] + source_errors,
            }

        except Exception as e:
            await self._fail_ingest_run(rid, str(e))
            for source in sources:
                await self._mark_source_failed(source, rid, str(e))
            raise

    async def _find_related_pages(self, source: dict) -> list[dict]:
        symbol = source.get("symbol", "")
        trade_date = source.get("trade_date", "")
        pages = []
        if symbol:
            pages.extend(await self.wiki_store.list_pages(symbol=symbol, limit=20))
        if trade_date:
            pages.extend(await self.wiki_store.list_pages(trade_date=trade_date, limit=20))
        # Deduplicate
        seen = set()
        unique = []
        for p in pages:
            pid = p.get("page_id")
            if pid not in seen:
                seen.add(pid)
                unique.append(p)
        return unique

    async def _find_related_pages_for_sources(self, sources: list[dict]) -> list[dict]:
        pages: list[dict] = []
        for source in sources:
            pages.extend(await self._find_related_pages(source))
        seen = set()
        unique = []
        for page in pages:
            page_id = page.get("page_id")
            if page_id not in seen:
                seen.add(page_id)
                unique.append(page)
        return unique

    def _validate_plan(self, plan: WikiUpdatePlan) -> dict:
        errors = validate_wiki_update_plan(plan, valid_source_ids=None)
        return {"errors": errors}

    def _error_run(self, trigger_type: str, source_id: str, error: str) -> dict:
        return {
            "run_id": "",
            "status": "failed",
            "source_ids": [source_id] if source_id else [],
            "pages_touched": [],
            "claims_touched": [],
            "warnings": [error],
        }

    def _new_run_id(self, key: str) -> str:
        now = _now_iso()
        date = now[:10]
        time = now[11:19].replace(":", "")
        micros = now[20:26] if len(now) >= 26 else "000000"
        return f"wiki_ingest:{date}:{time}{micros}:{_stable_hash(key, 8)}"

    async def _create_ingest_run(
        self,
        run_id: str,
        trigger_type: str,
        source_id: str,
        source_kind: str,
        mode: str,
        raw_run_id: str = "",
        status: str = "applying",
    ) -> None:
        now = _now_iso()
        async with __import__("aiosqlite").connect(self.wiki_store.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO wiki_ingest_runs
                   (run_id, trigger_type, source_id, raw_run_id, source_kind, status, mode, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, trigger_type, source_id, raw_run_id, source_kind, status, mode, now),
            )
            await db.commit()

    async def _update_ingest_run_status(self, run_id: str, status: str) -> None:
        async with __import__("aiosqlite").connect(self.wiki_store.db_path) as db:
            await db.execute(
                "UPDATE wiki_ingest_runs SET status = ? WHERE run_id = ?",
                (status, run_id),
            )
            await db.commit()

    async def _mark_source_running(self, source: dict, run_id: str, status: str) -> None:
        await self.wiki_store.upsert_source_state(
            source_id=source["source_id"],
            source_kind=source.get("source_kind", ""),
            raw_content_sha256=source.get("content_sha256", ""),
            wiki_status=status,
            latest_ingest_run_id=run_id,
            error="",
        )

    async def _mark_source_failed(self, source: dict, run_id: str, error: str) -> None:
        await self.wiki_store.upsert_source_state(
            source_id=source["source_id"],
            source_kind=source.get("source_kind", ""),
            raw_content_sha256=source.get("content_sha256", ""),
            wiki_status="failed",
            latest_ingest_run_id=run_id,
            page_ids=[],
            error=error,
        )

    async def _complete_ingest_run(self, run_id: str, pages_touched: list[dict], claims_touched: list[str]) -> None:
        now = _now_iso()
        async with __import__("aiosqlite").connect(self.wiki_store.db_path) as db:
            await db.execute(
                """UPDATE wiki_ingest_runs
                   SET status = ?, pages_touched_json = ?, claims_touched_json = ?, completed_at = ?
                   WHERE run_id = ?""",
                (
                    "completed",
                    __import__("json").dumps(pages_touched, ensure_ascii=False),
                    __import__("json").dumps(claims_touched, ensure_ascii=False),
                    now,
                    run_id,
                ),
            )
            await db.commit()

    async def _fail_ingest_run(self, run_id: str, error: str) -> None:
        now = _now_iso()
        async with __import__("aiosqlite").connect(self.wiki_store.db_path) as db:
            await db.execute(
                """UPDATE wiki_ingest_runs
                   SET status = ?, error = ?, completed_at = ?
                   WHERE run_id = ?""",
                ("failed", error, now, run_id),
            )
            await db.commit()
