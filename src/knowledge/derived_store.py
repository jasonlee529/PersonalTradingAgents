from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from src.config import Settings
from src.knowledge.derived_models import (
    BUILD_STATUS_COMPLETED,
    BUILD_STATUS_FAILED,
)


DERIVED_SCHEMA = """
CREATE TABLE IF NOT EXISTS derived_documents (
    doc_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    source_id TEXT DEFAULT '',
    page_id TEXT DEFAULT '',
    title TEXT DEFAULT '',
    path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derived_doc_type ON derived_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_derived_source_id ON derived_documents(source_id);
CREATE INDEX IF NOT EXISTS idx_derived_page_id ON derived_documents(page_id);

CREATE TABLE IF NOT EXISTS derived_chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    heading_path TEXT DEFAULT '',
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    token_estimate INTEGER DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derived_chunk_doc ON derived_chunks(doc_id);

CREATE TABLE IF NOT EXISTS derived_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derived_entity_type ON derived_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_derived_entity_key ON derived_entities(canonical_key);

CREATE TABLE IF NOT EXISTS derived_entity_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    chunk_id TEXT DEFAULT '',
    mention_text TEXT NOT NULL,
    mention_type TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derived_mention_entity ON derived_entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_derived_mention_doc ON derived_entity_mentions(doc_id);

CREATE TABLE IF NOT EXISTS derived_claim_refs (
    claim_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    chunk_id TEXT DEFAULT '',
    source_id TEXT DEFAULT '',
    page_id TEXT DEFAULT '',
    claim_type TEXT DEFAULT '',
    status TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derived_claim_claim ON derived_claim_refs(claim_id);
CREATE INDEX IF NOT EXISTS idx_derived_claim_doc ON derived_claim_refs(doc_id);

CREATE TABLE IF NOT EXISTS derived_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_derived_link_from ON derived_links(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_derived_link_to ON derived_links(to_type, to_id);

CREATE TABLE IF NOT EXISTS derived_build_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    documents_seen INTEGER DEFAULT 0,
    documents_indexed INTEGER DEFAULT 0,
    chunks_indexed INTEGER DEFAULT 0,
    entities_indexed INTEGER DEFAULT 0,
    error TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT DEFAULT ''
);
"""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class DerivedStore:
    """Persistent derived index store. Only writes to the configured derived store."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_dir = settings.derived_knowledge_dir
        self.db_path = settings.derived_knowledge_db_path

    def _resolve_derived_path(self, rel_path: Path) -> Path:
        derived_root = self.base_dir.resolve()
        abs_path = (self.base_dir / rel_path).resolve()
        try:
            abs_path.relative_to(derived_root)
        except ValueError as exc:
            raise ValueError(f"Derived path escapes derived root: {rel_path}") from exc
        return abs_path

    async def init_db(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "chunks").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "chunks" / "wiki").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "chunks" / "raw").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "summaries").mkdir(parents=True, exist_ok=True)
        (self.base_dir / "reports").mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(DERIVED_SCHEMA)
            await db.commit()

    async def clear(self) -> None:
        """Remove all derived data for a full rebuild."""
        async with aiosqlite.connect(self.db_path) as db:
            for table in [
                "derived_documents",
                "derived_chunks",
                "derived_entities",
                "derived_entity_mentions",
                "derived_claim_refs",
                "derived_links",
            ]:
                await db.execute(f"DELETE FROM {table}")
            await db.commit()

    async def upsert_document(self, doc: dict) -> dict:
        now = _now_iso()
        row = {
            "doc_id": doc["doc_id"],
            "doc_type": doc["doc_type"],
            "source_id": str(doc.get("source_id") or ""),
            "page_id": str(doc.get("page_id") or ""),
            "title": str(doc.get("title") or ""),
            "path": doc["path"],
            "content_sha256": doc["content_sha256"],
            "metadata_json": _json_dumps(doc.get("metadata") or {}),
            "created_at": str(doc.get("created_at") or now),
            "updated_at": str(doc.get("updated_at") or now),
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO derived_documents
                   (doc_id, doc_type, source_id, page_id, title, path, content_sha256,
                    metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(doc_id) DO UPDATE SET
                   doc_type=excluded.doc_type, source_id=excluded.source_id,
                   page_id=excluded.page_id, title=excluded.title,
                   path=excluded.path, content_sha256=excluded.content_sha256,
                   metadata_json=excluded.metadata_json,
                   updated_at=excluded.updated_at""",
                tuple(row[k] for k in (
                    "doc_id", "doc_type", "source_id", "page_id", "title", "path",
                    "content_sha256", "metadata_json", "created_at", "updated_at",
                )),
            )
            await db.commit()
        return row

    async def replace_chunks(self, doc_id: str, chunks: list[dict]) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM derived_chunks WHERE doc_id = ?", (doc_id,))
            for chunk in chunks:
                await db.execute(
                    """INSERT INTO derived_chunks
                       (chunk_id, doc_id, doc_type, ordinal, heading_path, text,
                        text_sha256, token_estimate, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk["chunk_id"],
                        doc_id,
                        chunk["doc_type"],
                        chunk["ordinal"],
                        chunk.get("heading_path", ""),
                        chunk["text"],
                        chunk.get("text_sha256") or _sha256_text(chunk["text"]),
                        chunk.get("token_estimate", 0),
                        _json_dumps(chunk.get("metadata") or {}),
                        now,
                    ),
                )
            await db.commit()

    async def upsert_entity(self, entity: dict) -> dict:
        now = _now_iso()
        row = {
            "entity_id": entity["entity_id"],
            "entity_type": entity["entity_type"],
            "name": entity["name"],
            "canonical_key": str(entity.get("canonical_key") or entity["name"]),
            "metadata_json": _json_dumps(entity.get("metadata") or {}),
            "created_at": str(entity.get("created_at") or now),
            "updated_at": str(entity.get("updated_at") or now),
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO derived_entities
                   (entity_id, entity_type, name, canonical_key, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(entity_id) DO UPDATE SET
                   entity_type=excluded.entity_type, name=excluded.name,
                   canonical_key=excluded.canonical_key, metadata_json=excluded.metadata_json,
                   updated_at=excluded.updated_at""",
                tuple(row[k] for k in (
                    "entity_id", "entity_type", "name", "canonical_key",
                    "metadata_json", "created_at", "updated_at",
                )),
            )
            await db.commit()
        return row

    async def replace_entity_mentions(self, doc_id: str, mentions: list[dict]) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM derived_entity_mentions WHERE doc_id = ?", (doc_id,))
            for m in mentions:
                await db.execute(
                    """INSERT INTO derived_entity_mentions
                       (entity_id, doc_id, chunk_id, mention_text, mention_type, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        m["entity_id"],
                        m["doc_id"],
                        m.get("chunk_id", ""),
                        m["mention_text"],
                        m.get("mention_type", ""),
                        _json_dumps(m.get("metadata") or {}),
                        now,
                    ),
                )
            await db.commit()

    async def add_entity_mentions(self, mentions: list[dict]) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            for m in mentions:
                await db.execute(
                    """INSERT INTO derived_entity_mentions
                       (entity_id, doc_id, chunk_id, mention_text, mention_type, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        m["entity_id"],
                        m["doc_id"],
                        m.get("chunk_id", ""),
                        m["mention_text"],
                        m.get("mention_type", ""),
                        _json_dumps(m.get("metadata") or {}),
                        now,
                    ),
                )
            await db.commit()

    async def replace_claim_refs(self, claim_id: str, refs: list[dict]) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM derived_claim_refs WHERE claim_id = ?", (claim_id,))
            for ref in refs:
                await db.execute(
                    """INSERT INTO derived_claim_refs
                       (claim_id, doc_id, chunk_id, source_id, page_id, claim_type, status, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ref["claim_id"],
                        ref["doc_id"],
                        ref.get("chunk_id", ""),
                        ref.get("source_id", ""),
                        ref.get("page_id", ""),
                        ref.get("claim_type", ""),
                        ref.get("status", ""),
                        _json_dumps(ref.get("metadata") or {}),
                        now,
                    ),
                )
            await db.commit()

    async def add_claim_refs(self, refs: list[dict]) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            for ref in refs:
                await db.execute(
                    """INSERT INTO derived_claim_refs
                       (claim_id, doc_id, chunk_id, source_id, page_id, claim_type, status, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ref["claim_id"],
                        ref["doc_id"],
                        ref.get("chunk_id", ""),
                        ref.get("source_id", ""),
                        ref.get("page_id", ""),
                        ref.get("claim_type", ""),
                        ref.get("status", ""),
                        _json_dumps(ref.get("metadata") or {}),
                        now,
                    ),
                )
            await db.commit()

    async def clear_links(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM derived_links")
            await db.commit()

    async def add_links(self, links: list[dict]) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            for link in links:
                await db.execute(
                    """INSERT INTO derived_links
                       (from_type, from_id, to_type, to_id, link_type, metadata_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        link["from_type"],
                        link["from_id"],
                        link["to_type"],
                        link["to_id"],
                        link["link_type"],
                        _json_dumps(link.get("metadata") or {}),
                        now,
                    ),
                )
            await db.commit()

    async def create_build_run(self, mode: str) -> str:
        run_id = f"build:{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO derived_build_runs
                   (run_id, mode, status, started_at)
                   VALUES (?, ?, ?, ?)""",
                (run_id, mode, "running", now),
            )
            await db.commit()
        return run_id

    async def complete_build_run(self, run_id: str, result: dict) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE derived_build_runs
                   SET status = ?, documents_seen = ?, documents_indexed = ?,
                       chunks_indexed = ?, entities_indexed = ?, completed_at = ?
                   WHERE run_id = ?""",
                (
                    result.get("status", BUILD_STATUS_COMPLETED),
                    result.get("documents_seen", 0),
                    result.get("documents_indexed", 0),
                    result.get("chunks_indexed", 0),
                    result.get("entities_indexed", 0),
                    now,
                    run_id,
                ),
            )
            await db.commit()

    async def fail_build_run(self, run_id: str, error: str) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE derived_build_runs
                   SET status = ?, error = ?, completed_at = ?
                   WHERE run_id = ?""",
                (BUILD_STATUS_FAILED, error, now, run_id),
            )
            await db.commit()

    async def stats(self) -> dict:
        counts: dict[str, int] = {}
        async with aiosqlite.connect(self.db_path) as db:
            for table in [
                "derived_documents",
                "derived_chunks",
                "derived_entities",
                "derived_entity_mentions",
                "derived_claim_refs",
                "derived_links",
                "derived_build_runs",
            ]:
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                    row = await cursor.fetchone()
                    counts[table] = row[0] if row else 0
        return counts

    async def get_document(self, doc_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM derived_documents WHERE doc_id = ?", (doc_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_documents(self, doc_type: str | None = None) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if doc_type:
                async with db.execute(
                    "SELECT * FROM derived_documents WHERE doc_type = ?", (doc_type,)
                ) as cursor:
                    return [dict(row) for row in await cursor.fetchall()]
            async with db.execute("SELECT * FROM derived_documents") as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def list_chunks_for_doc(self, doc_id: str) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM derived_chunks WHERE doc_id = ? ORDER BY ordinal", (doc_id,)
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def get_latest_build_run(self) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM derived_build_runs ORDER BY started_at DESC LIMIT 1"
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_entity(self, entity_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM derived_entities WHERE entity_id = ?", (entity_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def list_entities(self, entity_type: str | None = None) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if entity_type:
                async with db.execute(
                    "SELECT * FROM derived_entities WHERE entity_type = ?", (entity_type,)
                ) as cursor:
                    return [dict(row) for row in await cursor.fetchall()]
            async with db.execute("SELECT * FROM derived_entities") as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def list_claim_refs(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM derived_claim_refs") as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def list_links(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM derived_links") as cursor:
                return [dict(row) for row in await cursor.fetchall()]
