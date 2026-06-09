from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import yaml

from src.config import Settings
from src.knowledge.wiki_models import WIKI_PAGE_TYPES, WIKI_SOURCE_STATUSES


WIKI_SCHEMA = """
CREATE TABLE IF NOT EXISTS wiki_pages (
    page_id TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    content_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    symbol TEXT DEFAULT '',
    topic TEXT DEFAULT '',
    trade_date TEXT DEFAULT '',
    tags_json TEXT DEFAULT '[]',
    source_ids_json TEXT DEFAULT '[]',
    claim_ids_json TEXT DEFAULT '[]',
    status TEXT DEFAULT 'active',
    review_status TEXT DEFAULT 'generated',
    revision INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wiki_page_type ON wiki_pages(page_type);
CREATE INDEX IF NOT EXISTS idx_wiki_symbol ON wiki_pages(symbol);
CREATE INDEX IF NOT EXISTS idx_wiki_topic ON wiki_pages(topic);
CREATE INDEX IF NOT EXISTS idx_wiki_trade_date ON wiki_pages(trade_date);
CREATE INDEX IF NOT EXISTS idx_wiki_updated ON wiki_pages(updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wiki_slug ON wiki_pages(slug);

CREATE TABLE IF NOT EXISTS wiki_page_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_role TEXT DEFAULT 'evidence',
    claim_count INTEGER DEFAULT 0,
    first_used_at TEXT NOT NULL,
    last_used_at TEXT NOT NULL,
    UNIQUE(page_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_wiki_page_sources_page ON wiki_page_sources(page_id);
CREATE INDEX IF NOT EXISTS idx_wiki_page_sources_source ON wiki_page_sources(source_id);

CREATE TABLE IF NOT EXISTS wiki_page_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_page_id TEXT NOT NULL,
    to_page_id TEXT NOT NULL,
    link_text TEXT DEFAULT '',
    link_type TEXT DEFAULT 'wikilink',
    created_at TEXT NOT NULL,
    UNIQUE(from_page_id, to_page_id, link_text)
);
CREATE INDEX IF NOT EXISTS idx_wiki_links_from ON wiki_page_links(from_page_id);
CREATE INDEX IF NOT EXISTS idx_wiki_links_to ON wiki_page_links(to_page_id);

CREATE TABLE IF NOT EXISTS wiki_claims (
    claim_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    claim_type TEXT NOT NULL,
    statement TEXT NOT NULL,
    polarity TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    confidence REAL DEFAULT 0.0,
    source_ids_json TEXT DEFAULT '[]',
    page_ids_json TEXT DEFAULT '[]',
    contradicts_json TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claim_subject ON wiki_claims(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_claim_type ON wiki_claims(claim_type);
CREATE INDEX IF NOT EXISTS idx_claim_status ON wiki_claims(status);

CREATE TABLE IF NOT EXISTS wiki_ingest_runs (
    run_id TEXT PRIMARY KEY,
    trigger_type TEXT NOT NULL,
    source_id TEXT DEFAULT '',
    raw_run_id TEXT DEFAULT '',
    source_kind TEXT DEFAULT '',
    status TEXT NOT NULL,
    mode TEXT DEFAULT 'apply',
    plan_json TEXT DEFAULT '{}',
    pages_touched_json TEXT DEFAULT '[]',
    claims_touched_json TEXT DEFAULT '[]',
    error TEXT DEFAULT '',
    started_at TEXT NOT NULL,
    completed_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wiki_ingest_source ON wiki_ingest_runs(source_id);
CREATE INDEX IF NOT EXISTS idx_wiki_ingest_raw_run ON wiki_ingest_runs(raw_run_id);
CREATE INDEX IF NOT EXISTS idx_wiki_ingest_status ON wiki_ingest_runs(status);
CREATE INDEX IF NOT EXISTS idx_wiki_ingest_started ON wiki_ingest_runs(started_at);

CREATE TABLE IF NOT EXISTS wiki_source_state (
    source_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    raw_content_sha256 TEXT NOT NULL,
    wiki_status TEXT NOT NULL DEFAULT 'pending',
    latest_ingest_run_id TEXT DEFAULT '',
    page_ids_json TEXT DEFAULT '[]',
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wiki_source_state_status ON wiki_source_state(wiki_status);
CREATE INDEX IF NOT EXISTS idx_wiki_source_state_kind ON wiki_source_state(source_kind);
"""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _safe_filename(value: str, fallback: str = "unknown") -> str:
    clean = re.sub(r"[^0-9A-Za-z_\-.]+", "_", value.strip())
    return clean.strip("._") or fallback


def _build_page_path(page_type: str, metadata: dict) -> Path:
    symbol = str(metadata.get("symbol") or "").strip()
    trade_date = str(metadata.get("trade_date") or "").strip()
    slug = str(metadata.get("slug") or "").strip()
    topic = str(metadata.get("topic") or "").strip()
    source_kind = str(metadata.get("source_kind") or "").strip()
    source_id = str(metadata.get("source_id") or "").strip()

    if page_type == "home":
        return Path("index.md")
    if page_type == "log":
        return Path("log.md")
    if page_type == "stock_profile":
        return Path("pages") / "stocks" / f"{_safe_filename(symbol or 'unknown')}.md"
    if page_type == "stock_timeline":
        return Path("pages") / "stocks" / f"{_safe_filename(symbol or 'unknown')}_timeline.md"
    if page_type == "stock_analysis_runs":
        return Path("pages") / "stocks" / f"{_safe_filename(symbol or 'unknown')}_analysis_runs.md"
    if page_type == "topic":
        return Path("pages") / "topics" / f"{_safe_filename(slug or topic or 'unknown')}.md"
    if page_type == "daily_direction":
        return Path("pages") / "daily" / "directions" / f"{_safe_filename(trade_date or 'unknown')}.md"
    if page_type == "trade_month":
        month = trade_date[:7] if trade_date else "unknown"
        return Path("pages") / "daily" / "trade_logs" / f"{_safe_filename(month)}.md"
    if page_type == "portfolio_overview":
        return Path("pages") / "portfolio" / "overview.md"
    if page_type == "trade_review":
        return Path("pages") / "portfolio" / "trade_review.md"
    if page_type == "source_digest":
        safe_name = _safe_filename(slug or _sha256_text(source_id)[:8])
        kind_dir = _safe_filename(source_kind or "source")
        return Path("pages") / "sources" / kind_dir / f"{safe_name}.md"
    if page_type == "analysis_run_digest":
        safe_name = _safe_filename(slug or _sha256_text(source_id)[:8])
        return Path("pages") / "sources" / "stock_analysis" / f"{safe_name}.md"
    if page_type == "contradictions":
        return Path("pages") / "claims" / "contradictions.md"
    if page_type == "open_questions":
        return Path("pages") / "claims" / "open_questions.md"
    if page_type == "saved_query":
        safe_name = _safe_filename(slug or "query")
        return Path("pages") / "queries" / f"{safe_name}.md"
    return Path("pages") / "unknown" / f"{_safe_filename(page_type)}.md"


def _parse_wikilinks(markdown: str) -> list[tuple[str, str]]:
    results = []
    for m in re.finditer(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", markdown):
        target = m.group(1).strip()
        label = (m.group(2) or target).strip()
        results.append((target, label))
    return results


class WikiStore:
    """Persistent wiki page store backed by markdown files and SQLite index."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.knowledge_dir != Path("./data/knowledge"):
            if settings.wiki_knowledge_dir == Path("./data/knowledge/wiki"):
                settings.wiki_knowledge_dir = settings.knowledge_dir / "wiki"
            if settings.wiki_knowledge_db_path == Path("./data/knowledge/wiki/index.db"):
                settings.wiki_knowledge_db_path = settings.wiki_knowledge_dir / "index.db"
        self.base_dir = settings.wiki_knowledge_dir
        self.db_path = settings.wiki_knowledge_db_path
        self.schema_dir = settings.wiki_schema_dir

    async def init_db(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.schema_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "assets").mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(WIKI_SCHEMA)
            await db.commit()

        # Ensure base pages exist
        index_path = self._resolve_wiki_path(Path("index.md"))
        if not index_path.exists():
            await __import__("asyncio").to_thread(
                index_path.write_text,
                "# PersonalTradingAgents Wiki\n\n",
                encoding="utf-8",
                newline="\n",
            )
        log_path = self._resolve_wiki_path(Path("log.md"))
        if not log_path.exists():
            await __import__("asyncio").to_thread(
                log_path.write_text,
                "# Wiki Log\n\n",
                encoding="utf-8",
                newline="\n",
            )

        # Register base pages in DB (internal helper avoids recursion through upsert_page)
        await self._ensure_base_page_in_db(
            page_id="home:index",
            page_type="home",
            title="PersonalTradingAgents Wiki",
            slug="index",
            content_path="index.md",
        )
        await self._ensure_base_page_in_db(
            page_id="home:log",
            page_type="log",
            title="Wiki Log",
            slug="log",
            content_path="log.md",
        )

    async def _ensure_base_page_in_db(
        self,
        *,
        page_id: str,
        page_type: str,
        title: str,
        slug: str,
        content_path: str,
    ) -> None:
        abs_path = self._resolve_wiki_path(Path(content_path))
        if not abs_path.exists():
            return
        text = await __import__("asyncio").to_thread(
            abs_path.read_text, encoding="utf-8"
        )
        body = self._extract_body(text)
        content_sha256 = _sha256_text(body.rstrip() + "\n")
        now = _now_iso()

        # Query directly to avoid recursion through init_db in _get_page_record
        existing_sha256 = None
        existing_created_at = None
        existing_revision = None
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT content_sha256, created_at, revision FROM wiki_pages WHERE page_id = ?",
                (page_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    existing_sha256 = row["content_sha256"]
                    existing_created_at = row["created_at"]
                    existing_revision = row["revision"]

        if existing_sha256 == content_sha256:
            return

        created_at = existing_created_at or now
        revision = int(existing_revision or 1)
        if existing_sha256 is not None and content_sha256 != existing_sha256:
            revision += 1

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO wiki_pages
                   (page_id, page_type, title, slug, content_path, content_sha256,
                    symbol, topic, trade_date, tags_json, source_ids_json, claim_ids_json,
                    status, review_status, revision, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(page_id) DO UPDATE SET
                   page_type=excluded.page_type, title=excluded.title, slug=excluded.slug,
                   content_path=excluded.content_path, content_sha256=excluded.content_sha256,
                   updated_at=excluded.updated_at, revision=excluded.revision""",
                (
                    page_id, page_type, title, slug, content_path, content_sha256,
                    "", "", "", _json_dumps([]), _json_dumps([]), _json_dumps([]),
                    "active", "generated", revision, created_at, now,
                ),
            )
            await db.commit()

    def _resolve_wiki_path(self, rel_path: Path) -> Path:
        wiki_root = self.base_dir.resolve()
        abs_path = (self.base_dir / rel_path).resolve()
        try:
            abs_path.relative_to(wiki_root)
        except ValueError as exc:
            raise ValueError(f"Wiki path escapes wiki root: {rel_path}") from exc
        return abs_path

    async def upsert_page(
        self,
        *,
        page_id: str,
        page_type: str,
        title: str,
        slug: str,
        markdown: str,
        metadata: dict | None = None,
    ) -> dict:
        if page_type not in WIKI_PAGE_TYPES:
            raise ValueError(f"Unsupported wiki page_type: {page_type}")
        if not page_id.strip():
            raise ValueError("page_id cannot be empty")
        if not title.strip():
            raise ValueError("title cannot be empty")
        if not slug.strip():
            raise ValueError("slug cannot be empty")

        await self.init_db()
        meta = dict(metadata or {})
        now = _now_iso()

        symbol = str(meta.get("symbol") or "").strip()
        topic = str(meta.get("topic") or "").strip()
        trade_date = str(meta.get("trade_date") or "").strip()
        tags = _as_list(meta.get("tags"))
        source_ids = _as_list(meta.get("source_ids"))
        claim_ids = _as_list(meta.get("claim_ids"))
        status = str(meta.get("status") or "active").strip()
        review_status = str(meta.get("review_status") or "generated").strip()

        rel_path = _build_page_path(page_type, meta)
        abs_path = self._resolve_wiki_path(rel_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        body = markdown.rstrip() + "\n"
        content_sha256 = _sha256_text(body)

        existing = await self._get_page_record(page_id)
        revision = 1
        created_at = now
        if existing:
            revision = int(existing.get("revision") or 1)
            if content_sha256 != existing.get("content_sha256"):
                revision += 1
            created_at = existing.get("created_at") or now

        frontmatter = {
            "page_id": page_id,
            "page_type": page_type,
            "title": title.strip(),
            "slug": slug,
            "symbol": symbol,
            "topic": topic,
            "trade_date": trade_date,
            "tags": tags,
            "source_ids": source_ids,
            "claim_ids": claim_ids,
            "status": status,
            "review_status": review_status,
            "revision": revision,
            "created_at": created_at,
            "updated_at": now,
            **{k: v for k, v in meta.items() if k not in {
                "page_id", "page_type", "title", "slug", "symbol", "topic", "trade_date",
                "tags", "source_ids", "claim_ids", "status", "review_status", "revision",
                "created_at", "updated_at",
            }},
        }
        text = f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{body}"
        await __import__("asyncio").to_thread(abs_path.write_text, text, encoding="utf-8", newline="\n")

        row = {
            "page_id": page_id,
            "page_type": page_type,
            "title": title.strip(),
            "slug": slug,
            "content_path": rel_path.as_posix(),
            "content_sha256": content_sha256,
            "symbol": symbol,
            "topic": topic,
            "trade_date": trade_date,
            "tags_json": _json_dumps(tags),
            "source_ids_json": _json_dumps(source_ids),
            "claim_ids_json": _json_dumps(claim_ids),
            "status": status,
            "review_status": review_status,
            "revision": revision,
            "created_at": created_at,
            "updated_at": now,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO wiki_pages
                   (page_id, page_type, title, slug, content_path, content_sha256,
                    symbol, topic, trade_date, tags_json, source_ids_json, claim_ids_json,
                    status, review_status, revision, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(page_id) DO UPDATE SET
                   page_type=excluded.page_type, title=excluded.title, slug=excluded.slug,
                   content_path=excluded.content_path, content_sha256=excluded.content_sha256,
                   symbol=excluded.symbol, topic=excluded.topic, trade_date=excluded.trade_date,
                   tags_json=excluded.tags_json, source_ids_json=excluded.source_ids_json,
                   claim_ids_json=excluded.claim_ids_json, status=excluded.status,
                   review_status=excluded.review_status, revision=excluded.revision,
                   updated_at=excluded.updated_at""",
                tuple(row[k] for k in (
                    "page_id", "page_type", "title", "slug", "content_path", "content_sha256",
                    "symbol", "topic", "trade_date", "tags_json", "source_ids_json", "claim_ids_json",
                    "status", "review_status", "revision", "created_at", "updated_at",
                )),
            )
            await db.commit()

        await self.rebuild_page_links(page_id)

        for sid in source_ids:
            await self.link_page_source(page_id, sid, source_role="evidence")

        return {**self._normalise_page_record(row), "content_path": str(rel_path)}

    async def read_page(self, page_id: str) -> dict:
        row = await self._get_page_record(page_id)
        if not row:
            raise FileNotFoundError(page_id)
        abs_path = self._resolve_wiki_path(Path(row["content_path"]))
        text = await __import__("asyncio").to_thread(abs_path.read_text, encoding="utf-8")
        row["content"] = text
        row["markdown"] = self._extract_body(text)
        row["frontmatter"] = self._extract_frontmatter(text)
        return row

    async def get_page_by_slug(self, slug: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM wiki_pages WHERE slug = ?", (slug,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._normalise_page_record(dict(row)) if row else None

    async def list_pages(
        self,
        *,
        page_type: str | None = None,
        symbol: str | None = None,
        topic: str | None = None,
        trade_date: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        await self.init_db()
        clauses: list[str] = []
        params: list[Any] = []
        if page_type:
            clauses.append("page_type = ?")
            params.append(page_type)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if topic:
            clauses.append("topic = ?")
            params.append(topic)
        if trade_date:
            clauses.append("trade_date = ?")
            params.append(trade_date)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT * FROM wiki_pages"
            + where
            + " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        )
        db_limit = 1000 if q else max(1, min(limit, 200))
        db_offset = 0 if q else max(0, offset)
        params.extend([db_limit, db_offset])
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                rows = [self._normalise_page_record(dict(row)) for row in await cursor.fetchall()]

        if q:
            q_lower = q.lower()
            filtered = []
            for row in rows:
                if q_lower in (row.get("page_id") or "").lower():
                    filtered.append(row)
                    continue
                if q_lower in (row.get("title") or "").lower():
                    filtered.append(row)
                    continue
                if q_lower in (row.get("slug") or "").lower():
                    filtered.append(row)
                    continue
                try:
                    abs_path = self._resolve_wiki_path(Path(row["content_path"]))
                    text = await __import__("asyncio").to_thread(abs_path.read_text, encoding="utf-8")
                    body = self._extract_body(text)
                    if q_lower in body.lower():
                        filtered.append(row)
                except Exception:
                    pass
            rows = filtered[offset:offset + limit]

        return rows

    async def patch_section(
        self,
        page_id: str,
        *,
        section_id: str,
        markdown: str,
        mode: str = "replace",
    ) -> dict:
        page = await self.read_page(page_id)
        body = page.get("markdown", "")
        frontmatter = dict(page.get("frontmatter") or {})

        start_marker = f"<!-- wiki-section:start:{section_id} -->"
        end_marker = f"<!-- wiki-section:end:{section_id} -->"

        start_idx = body.find(start_marker)
        end_idx = body.find(end_marker)

        if start_idx == -1 or end_idx == -1:
            allowed_auto_create = {
                "stock_profile", "stock_timeline", "stock_analysis_runs",
                "topic", "daily_direction", "trade_month",
                "portfolio_overview", "trade_review",
            }
            page_type = page.get("page_type", "")
            if page_type not in allowed_auto_create:
                raise ValueError(f"Section {section_id} not found and auto-create not allowed for {page_type}")
            new_section = f"{start_marker}\n{markdown.rstrip()}\n{end_marker}"
            if body.rstrip():
                body = body.rstrip() + "\n\n" + new_section + "\n"
            else:
                body = new_section + "\n"
        else:
            before = body[:start_idx + len(start_marker)]
            after = body[end_idx:]
            current = body[start_idx + len(start_marker):end_idx].strip("\n")

            if mode == "replace":
                new_content = markdown.rstrip()
            elif mode == "append":
                new_content = (current + "\n" + markdown).rstrip()
            elif mode == "prepend":
                new_content = (markdown + "\n" + current).rstrip()
            else:
                raise ValueError(f"Unknown patch mode: {mode}")
            body = before + "\n" + new_content + "\n" + after

        meta = {
            **frontmatter,
            "revision": int(frontmatter.get("revision") or 1) + 1,
        }
        return await self.upsert_page(
            page_id=page_id,
            page_type=page["page_type"],
            title=page["title"],
            slug=page["slug"],
            markdown=body,
            metadata=meta,
        )

    async def append_log(self, markdown_entry: str) -> dict:
        log_path = self._resolve_wiki_path(Path("log.md"))
        log_path.parent.mkdir(parents=True, exist_ok=True)

        now = _now_iso()
        if log_path.exists():
            existing = await __import__("asyncio").to_thread(log_path.read_text, encoding="utf-8")
        else:
            existing = "# Wiki Log\n\n"

        entry = markdown_entry.rstrip() + "\n\n"
        new_content = existing.rstrip() + "\n\n" + entry
        await __import__("asyncio").to_thread(log_path.write_text, new_content, encoding="utf-8", newline="\n")

        return {"log_path": str(log_path), "appended_at": now}

    async def upsert_claim(self, claim: dict) -> dict:
        if not claim.get("source_ids"):
            raise ValueError("Claim must have at least one source_id")

        now = _now_iso()
        claim_id = str(claim.get("claim_id") or "").strip()
        if not claim_id:
            claim_id = f"claim:{_sha256_text(claim.get('statement', '') + now)[:16]}"

        row = {
            "claim_id": claim_id,
            "subject_type": str(claim.get("subject_type") or ""),
            "subject_id": str(claim.get("subject_id") or ""),
            "claim_type": str(claim.get("claim_type") or ""),
            "statement": str(claim.get("statement") or ""),
            "polarity": str(claim.get("polarity") or ""),
            "status": str(claim.get("status") or "active"),
            "confidence": float(claim.get("confidence") or 0.0),
            "source_ids_json": _json_dumps(_as_list(claim.get("source_ids"))),
            "page_ids_json": _json_dumps(_as_list(claim.get("page_ids"))),
            "contradicts_json": _json_dumps(_as_list(claim.get("contradicts"))),
            "metadata_json": _json_dumps(dict(claim.get("metadata") or {})),
            "created_at": str(claim.get("created_at") or now),
            "updated_at": now,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO wiki_claims
                   (claim_id, subject_type, subject_id, claim_type, statement, polarity,
                    status, confidence, source_ids_json, page_ids_json, contradicts_json,
                    metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(claim_id) DO UPDATE SET
                   subject_type=excluded.subject_type, subject_id=excluded.subject_id,
                   claim_type=excluded.claim_type, statement=excluded.statement,
                   polarity=excluded.polarity, status=excluded.status,
                   confidence=excluded.confidence, source_ids_json=excluded.source_ids_json,
                   page_ids_json=excluded.page_ids_json, contradicts_json=excluded.contradicts_json,
                   metadata_json=excluded.metadata_json, updated_at=excluded.updated_at""",
                tuple(row[k] for k in (
                    "claim_id", "subject_type", "subject_id", "claim_type", "statement", "polarity",
                    "status", "confidence", "source_ids_json", "page_ids_json", "contradicts_json",
                    "metadata_json", "created_at", "updated_at",
                )),
            )
            await db.commit()
        return {**row, "source_ids": _as_list(claim.get("source_ids")), "page_ids": _as_list(claim.get("page_ids"))}

    async def link_page_source(
        self,
        page_id: str,
        source_id: str,
        *,
        source_role: str = "evidence",
        claim_count: int = 0,
    ) -> None:
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO wiki_page_sources
                   (page_id, source_id, source_role, claim_count, first_used_at, last_used_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(page_id, source_id) DO UPDATE SET
                   source_role=excluded.source_role, claim_count=excluded.claim_count,
                   last_used_at=excluded.last_used_at""",
                (page_id, source_id, source_role, claim_count, now, now),
            )
            await db.commit()

    async def rebuild_page_links(self, page_id: str) -> None:
        page = await self.read_page(page_id)
        markdown = page.get("markdown", "")
        links = _parse_wikilinks(markdown)
        now = _now_iso()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM wiki_page_links WHERE from_page_id = ?", (page_id,)
            )
            for target, label in links:
                to_page_id = target
                slug_row = await db.execute(
                    "SELECT page_id FROM wiki_pages WHERE slug = ?", (target,)
                )
                found = await slug_row.fetchone()
                if found:
                    to_page_id = found[0]
                await db.execute(
                    """INSERT INTO wiki_page_links
                       (from_page_id, to_page_id, link_text, link_type, created_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(from_page_id, to_page_id, link_text) DO NOTHING""",
                    (page_id, to_page_id, label, "wikilink", now),
                )
            await db.commit()

    async def rebuild_index(self) -> dict:
        pages = await self.list_pages(limit=1000)
        pending_sources = await self.list_source_states(status="pending", limit=1000)
        active_claims = await self._list_active_claims(limit=1000)

        index_md = self._render_index(pages, pending_sources, active_claims)
        index_path = self._resolve_wiki_path(Path("index.md"))
        await __import__("asyncio").to_thread(
            index_path.write_text, index_md, encoding="utf-8", newline="\n"
        )

        # Refresh base page DB row and links
        await self._ensure_base_page_in_db(
            page_id="home:index",
            page_type="home",
            title="PersonalTradingAgents Wiki",
            slug="index",
            content_path="index.md",
        )
        await self.rebuild_page_links("home:index")

        # Ensure placeholder pages exist for index links
        await self._ensure_placeholder_page(
            page_id="claims:contradictions",
            page_type="contradictions",
            title="观点冲突",
            slug="pages/claims/contradictions",
        )
        await self._ensure_placeholder_page(
            page_id="claims:open_questions",
            page_type="open_questions",
            title="待验证问题",
            slug="pages/claims/open_questions",
        )
        await self._ensure_placeholder_page(
            page_id="portfolio:overview",
            page_type="portfolio_overview",
            title="组合总览",
            slug="pages/portfolio/overview",
        )
        await self._ensure_placeholder_page(
            page_id="portfolio:trade_review",
            page_type="trade_review",
            title="交易复盘",
            slug="pages/portfolio/trade_review",
        )

        return {"index_path": str(index_path), "page_count": len(pages)}

    async def _ensure_placeholder_page(
        self,
        *,
        page_id: str,
        page_type: str,
        title: str,
        slug: str,
    ) -> None:
        existing = await self._get_page_record(page_id)
        if existing:
            return
        rel_path = _build_page_path(page_type, {"slug": slug})
        abs_path = self._resolve_wiki_path(rel_path)
        if not abs_path.exists():
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            body = f"# {title}\n\n"
            await __import__("asyncio").to_thread(
                abs_path.write_text, body, encoding="utf-8", newline="\n"
            )
        await self._ensure_base_page_in_db(
            page_id=page_id,
            page_type=page_type,
            title=title,
            slug=slug,
            content_path=rel_path.as_posix(),
        )
        await self.rebuild_page_links(page_id)

    @staticmethod
    def _render_index(pages: list[dict], pending_sources: list[dict], active_claims: list[dict]) -> str:
        lines = ["# 知识库\n"]

        stock_pages = [p for p in pages if p.get("page_type") == "stock_profile"]
        topic_pages = [p for p in pages if p.get("page_type") == "topic"]
        digest_pages = [p for p in pages if p.get("page_type") in ("source_digest", "analysis_run_digest")]
        recent = sorted(pages, key=lambda p: p.get("updated_at", ""), reverse=True)[:20]

        lines.append("## 最近更新\n")
        if recent:
            for p in recent:
                slug = p.get("slug", "")
                title = p.get("title", "")
                lines.append(f"- [[{slug}|{title}]]")
        else:
            lines.append("- 暂无页面")
        lines.append("")

        lines.append("## 股票\n")
        if stock_pages:
            for p in stock_pages:
                slug = p.get("slug", "")
                title = p.get("title", "")
                lines.append(f"- [[{slug}|{title}]]")
        else:
            lines.append("- 暂无股票页面")
        lines.append("")

        lines.append("## 主题\n")
        if topic_pages:
            for p in topic_pages:
                slug = p.get("slug", "")
                title = p.get("title", "")
                lines.append(f"- [[{slug}|{title}]]")
        else:
            lines.append("- 暂无主题页面")
        lines.append("")

        lines.append("## 来源摘要\n")
        if digest_pages:
            for p in digest_pages[:10]:
                slug = p.get("slug", "")
                title = p.get("title", "")
                lines.append(f"- [[{slug}|{title}]]")
        else:
            lines.append("- 暂无来源摘要")
        lines.append("")

        lines.append(f"## 待处理来源 ({len(pending_sources)})\n")
        if pending_sources:
            lines.append("- 有原始材料等待 ingest")
        else:
            lines.append("- 无待处理来源")
        lines.append("")

        lines.append("## 风险和冲突\n")
        lines.append("- [[pages/claims/contradictions|观点冲突]]")
        lines.append("- [[pages/claims/open_questions|待验证问题]]")
        lines.append("")

        lines.append("## 操作\n")
        lines.append("- [[pages/portfolio/overview|组合总览]]")
        lines.append("- [[pages/portfolio/trade_review|交易复盘]]")
        lines.append("")

        return "\n".join(lines) + "\n"

    async def verify_page(self, page_id: str) -> bool:
        page = await self.read_page(page_id)
        actual = _sha256_text(page["markdown"].rstrip() + "\n")
        return actual == page["content_sha256"]

    async def get_source_state(self, source_id: str) -> dict | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM wiki_source_state WHERE source_id = ?", (source_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._normalise_source_state_record(dict(row)) if row else None

    async def upsert_source_state(
        self,
        source_id: str,
        source_kind: str,
        raw_content_sha256: str,
        wiki_status: str,
        *,
        latest_ingest_run_id: str = "",
        page_ids: list[str] | None = None,
        error: str = "",
    ) -> dict:
        if wiki_status not in WIKI_SOURCE_STATUSES:
            raise ValueError(f"Invalid wiki_status: {wiki_status}")
        now = _now_iso()
        row = {
            "source_id": source_id,
            "source_kind": source_kind,
            "raw_content_sha256": raw_content_sha256,
            "wiki_status": wiki_status,
            "latest_ingest_run_id": latest_ingest_run_id,
            "page_ids_json": _json_dumps(page_ids or []),
            "error": error,
            "created_at": now,
            "updated_at": now,
        }
        existing = await self.get_source_state(source_id)
        if existing:
            row["created_at"] = existing.get("created_at") or now
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO wiki_source_state
                   (source_id, source_kind, raw_content_sha256, wiki_status,
                    latest_ingest_run_id, page_ids_json, error, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET
                   source_kind=excluded.source_kind, raw_content_sha256=excluded.raw_content_sha256,
                   wiki_status=excluded.wiki_status, latest_ingest_run_id=excluded.latest_ingest_run_id,
                   page_ids_json=excluded.page_ids_json, error=excluded.error,
                   updated_at=excluded.updated_at""",
                tuple(row[k] for k in (
                    "source_id", "source_kind", "raw_content_sha256", "wiki_status",
                    "latest_ingest_run_id", "page_ids_json", "error", "created_at", "updated_at",
                )),
            )
            await db.commit()
        return self._normalise_source_state_record(row)

    async def list_source_states(
        self,
        *,
        status: str | None = None,
        source_kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        await self.init_db()
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("wiki_status = ?")
            params.append(status)
        if source_kind:
            clauses.append("source_kind = ?")
            params.append(source_kind)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT * FROM wiki_source_state"
            + where
            + " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([max(1, min(limit, 200)), max(0, offset)])
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                return [self._normalise_source_state_record(dict(row)) for row in await cursor.fetchall()]

    async def _get_page_record(self, page_id: str) -> dict | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM wiki_pages WHERE page_id = ?", (page_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._normalise_page_record(dict(row)) if row else None

    async def _list_active_claims(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM wiki_claims WHERE status = 'active' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def _extract_body(text: str) -> str:
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                body = text[end + 4:]
                return body.lstrip("\n")
        return text

    @staticmethod
    def _extract_frontmatter(text: str) -> dict:
        if not text.startswith("---\n"):
            return {}
        end = text.find("\n---", 4)
        if end == -1:
            return {}
        raw = text[4:end]
        loaded = yaml.safe_load(raw) or {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _normalise_page_record(row: dict) -> dict:
        result = dict(row)
        for json_field, public_field, fallback in [
            ("tags_json", "tags", []),
            ("source_ids_json", "source_ids", []),
            ("claim_ids_json", "claim_ids", []),
        ]:
            raw = result.get(json_field)
            try:
                result[public_field] = json.loads(raw) if raw else fallback
            except (TypeError, json.JSONDecodeError):
                result[public_field] = fallback
        return result

    @staticmethod
    def _normalise_source_state_record(row: dict) -> dict:
        result = dict(row)
        for json_field, public_field, fallback in [
            ("page_ids_json", "page_ids", []),
        ]:
            raw = result.get(json_field)
            try:
                result[public_field] = json.loads(raw) if raw else fallback
            except (TypeError, json.JSONDecodeError):
                result[public_field] = fallback
        return result

    async def save_plan_to_run(self, run_id: str, plan: dict) -> None:
        """Save a plan to the ingest run record."""
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE wiki_ingest_runs SET plan_json = ? WHERE run_id = ?",
                (json.dumps(plan, ensure_ascii=False), run_id),
            )
            await db.commit()
