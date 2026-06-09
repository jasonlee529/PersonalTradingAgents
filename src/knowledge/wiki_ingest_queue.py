from __future__ import annotations

import asyncio
import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiosqlite

from src.config import Settings
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_ingestor import WikiIngestor
from src.knowledge.wiki_models import WIKI_RUNNING_SOURCE_STATUSES
from src.knowledge.wiki_schema import WikiSchema
from src.knowledge.wiki_store import WikiStore

logger = logging.getLogger(__name__)

MAX_RUNNING_WIKI_INGEST_SOURCES = 5


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _stable_hash(value: str, length: int = 16) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _new_run_id(key: str) -> str:
    now = _now_iso()
    return (
        f"wiki_ingest:{now[:10]}:{now[11:19].replace(':', '')}"
        f"{now[20:26] if len(now) >= 26 else '000000'}:{_stable_hash(key, 8)}"
    )


@dataclass(frozen=True)
class WikiIngestQueueItem:
    kind: str
    run_id: str
    source_id: str = ""
    raw_run_id: str = ""
    force: bool = False


class WikiIngestQueue:
    """Accept wiki ingest quickly and execute writes on a dedicated worker thread."""

    def __init__(
        self,
        settings: Settings,
        raw_store: RawStore,
        wiki_store: WikiStore,
        *,
        max_running_sources: int = MAX_RUNNING_WIKI_INGEST_SOURCES,
    ):
        self.settings = settings
        self.raw_store = raw_store
        self.wiki_store = wiki_store
        self.max_running_sources = max_running_sources
        self._items: queue.Queue[WikiIngestQueueItem | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._enqueue_lock: asyncio.Lock | None = None
        self._enqueue_lock_loop: asyncio.AbstractEventLoop | None = None

    async def recover_interrupted(self) -> int:
        """Clear stale running states left behind by a previous process."""
        states = []
        for status in WIKI_RUNNING_SOURCE_STATUSES:
            states.extend(await self.wiki_store.list_source_states(status=status, limit=200))
        if not states:
            return 0

        now = _now_iso()
        message = "Wiki ingest was interrupted before completion; retry to run it again."
        run_ids = {s.get("latest_ingest_run_id", "") for s in states if s.get("latest_ingest_run_id")}

        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            for state in states:
                await db.execute(
                    """UPDATE wiki_source_state
                       SET wiki_status = ?, error = ?, updated_at = ?
                       WHERE source_id = ?""",
                    ("failed", message, now, state["source_id"]),
                )
            for run_id in run_ids:
                await db.execute(
                    """UPDATE wiki_ingest_runs
                       SET status = ?, error = ?, completed_at = ?
                       WHERE run_id = ? AND status IN ('queued', 'pending', 'planning', 'applying')""",
                    ("failed", message, now, run_id),
                )
            await db.commit()

        logger.warning("Recovered %s interrupted wiki ingest source states", len(states))
        return len(states)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker_main,
            name="wiki-ingest-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._items.put(None)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None

    async def enqueue_source(self, source_id: str, *, force: bool = False) -> dict[str, Any]:
        lock = self._get_enqueue_lock()
        async with lock:
            source = await self.raw_store.read_source(source_id)
            state = await self.wiki_store.get_source_state(source_id)

            if self._is_running_state(state):
                return self._running_response(state, [source_id])

            if state and state.get("wiki_status") == "processed" and not force:
                return {
                    "run_id": state.get("latest_ingest_run_id", ""),
                    "status": "skipped",
                    "source_ids": [source_id],
                    "pages_touched": state.get("page_ids", []),
                    "claims_touched": [],
                    "warnings": ["Source already processed"],
                }

            running_count = await self._count_running_sources()
            if running_count >= self.max_running_sources:
                raise RuntimeError(f"Wiki ingest running limit reached: {self.max_running_sources}")

            run_id = _new_run_id(source_id)
            await self._create_run(
                run_id=run_id,
                trigger_type="source",
                source_id=source_id,
                raw_run_id="",
                source_kind=source.get("source_kind", ""),
                status="queued",
            )
            await self.wiki_store.upsert_source_state(
                source_id=source_id,
                source_kind=source.get("source_kind", ""),
                raw_content_sha256=source.get("content_sha256", ""),
                wiki_status="queued",
                latest_ingest_run_id=run_id,
                page_ids=state.get("page_ids", []) if state else [],
                error="",
            )
            self._items.put(WikiIngestQueueItem(kind="source", run_id=run_id, source_id=source_id, force=force))
            return self._queued_response(run_id, [source_id])

    async def enqueue_analysis_run(self, raw_run_id: str, *, force: bool = False) -> dict[str, Any]:
        lock = self._get_enqueue_lock()
        async with lock:
            all_sources = await self.raw_store.list_sources(source_kind="stock_analysis", limit=200)
            sources = [
                s for s in all_sources
                if s.get("metadata", {}).get("run_id") == raw_run_id
            ]
            if not sources:
                raise FileNotFoundError(raw_run_id)

            states = {
                source["source_id"]: await self.wiki_store.get_source_state(source["source_id"])
                for source in sources
            }
            running_states = [s for s in states.values() if self._is_running_state(s)]
            if running_states:
                return self._running_response(running_states[0], [s["source_id"] for s in sources])

            if (
                not force
                and states
                and all(s and s.get("wiki_status") == "processed" for s in states.values())
            ):
                return {
                    "run_id": "",
                    "status": "skipped",
                    "source_ids": [s["source_id"] for s in sources],
                    "pages_touched": [],
                    "claims_touched": [],
                    "warnings": ["All sources already processed"],
                }

            running_count = await self._count_running_sources()
            required_slots = len([s for s in sources if not self._is_running_state(states.get(s["source_id"]))])
            if running_count + required_slots > self.max_running_sources:
                raise RuntimeError(f"Wiki ingest running limit reached: {self.max_running_sources}")

            run_id = _new_run_id(raw_run_id)
            await self._create_run(
                run_id=run_id,
                trigger_type="analysis_run",
                source_id="",
                raw_run_id=raw_run_id,
                source_kind=sources[0].get("source_kind", ""),
                status="queued",
            )
            for source in sources:
                state = states.get(source["source_id"])
                await self.wiki_store.upsert_source_state(
                    source_id=source["source_id"],
                    source_kind=source.get("source_kind", ""),
                    raw_content_sha256=source.get("content_sha256", ""),
                    wiki_status="queued",
                    latest_ingest_run_id=run_id,
                    page_ids=state.get("page_ids", []) if state else [],
                    error="",
                )
            self._items.put(
                WikiIngestQueueItem(
                    kind="analysis_run",
                    run_id=run_id,
                    raw_run_id=raw_run_id,
                    force=force,
                )
            )
            return self._queued_response(run_id, [s["source_id"] for s in sources])

    async def enqueue_batch(self, source_ids: list[str]) -> dict[str, Any]:
        results = []
        for source_id in source_ids[: self.settings.wiki_ingest_batch_size]:
            try:
                result = await self.enqueue_source(source_id)
                results.append({"source_id": source_id, **result})
            except RuntimeError as exc:
                results.append({"source_id": source_id, "status": "rejected", "error": str(exc)})
                break
            except FileNotFoundError:
                results.append({"source_id": source_id, "status": "failed", "error": "Source not found"})
        return {"batch_status": "queued", "results": results}

    def _get_enqueue_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._enqueue_lock is None or self._enqueue_lock_loop is not loop:
            self._enqueue_lock = asyncio.Lock()
            self._enqueue_lock_loop = loop
        return self._enqueue_lock

    @staticmethod
    def _is_running_state(state: dict | None) -> bool:
        return bool(state and state.get("wiki_status") in WIKI_RUNNING_SOURCE_STATUSES)

    @staticmethod
    def _queued_response(run_id: str, source_ids: list[str]) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "status": "queued",
            "source_ids": source_ids,
            "pages_touched": [],
            "claims_touched": [],
            "warnings": [],
        }

    @staticmethod
    def _running_response(state: dict | None, source_ids: list[str]) -> dict[str, Any]:
        return {
            "run_id": state.get("latest_ingest_run_id", "") if state else "",
            "status": state.get("wiki_status", "queued") if state else "queued",
            "source_ids": source_ids,
            "pages_touched": state.get("page_ids", []) if state else [],
            "claims_touched": [],
            "warnings": ["Source already queued or running"],
        }

    async def _count_running_sources(self) -> int:
        placeholders = ",".join("?" for _ in WIKI_RUNNING_SOURCE_STATUSES)
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            async with db.execute(
                f"SELECT COUNT(*) FROM wiki_source_state WHERE wiki_status IN ({placeholders})",
                tuple(WIKI_RUNNING_SOURCE_STATUSES),
            ) as cursor:
                row = await cursor.fetchone()
                return int(row[0] if row else 0)

    async def _create_run(
        self,
        *,
        run_id: str,
        trigger_type: str,
        source_id: str,
        raw_run_id: str,
        source_kind: str,
        status: str,
    ) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO wiki_ingest_runs
                   (run_id, trigger_type, source_id, raw_run_id, source_kind, status, mode, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, trigger_type, source_id, raw_run_id, source_kind, status, "apply", now),
            )
            await db.commit()

    def _worker_main(self) -> None:
        while not self._stop.is_set():
            item = self._items.get()
            if item is None:
                break
            try:
                asyncio.run(self._run_item(item))
            except Exception:
                logger.exception("Wiki ingest queue item failed: %s", item)
            finally:
                self._items.task_done()

    async def _run_item(self, item: WikiIngestQueueItem) -> None:
        settings = self._settings_for_item()
        schema = WikiSchema(settings)
        ingestor = WikiIngestor(settings, self.raw_store, self.wiki_store, schema=schema)
        if item.kind == "source":
            await ingestor.ingest_source(item.source_id, force=item.force, run_id=item.run_id)
            return
        if item.kind == "analysis_run":
            await ingestor.ingest_analysis_run(
                item.raw_run_id,
                force=item.force,
                ingest_run_id=item.run_id,
            )
            return
        raise ValueError(f"Unsupported wiki ingest queue item kind: {item.kind}")

    def _settings_for_item(self) -> Settings:
        """Refresh user-editable LLM settings while preserving service paths."""
        try:
            fresh = Settings(_env_file=self.settings.settings_env_path)
        except Exception:
            logger.exception("Failed to refresh settings for wiki ingest; using in-memory settings")
            return self.settings

        from src.config import PERSISTED_SETTINGS_FIELDS

        fields = tuple(PERSISTED_SETTINGS_FIELDS) + ("test_mode",)
        return self.settings.model_copy(
            deep=True,
            update={field: getattr(fresh, field) for field in fields},
        )
