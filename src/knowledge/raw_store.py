from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import yaml

from src.config import Settings
from src.knowledge.raw_models import RAW_ORIGINS, RAW_SOURCE_KINDS, label_for_source_kind
from src.utils.ticker import safe_ticker_component


RAW_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_sources (
    source_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    origin TEXT NOT NULL,
    title TEXT NOT NULL,
    content_path TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    canonical_uri TEXT DEFAULT '',
    source_ref TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    symbol TEXT DEFAULT '',
    symbols_json TEXT DEFAULT '[]',
    trade_date TEXT DEFAULT '',
    published_at TEXT DEFAULT '',
    occurred_at TEXT DEFAULT '',
    captured_at TEXT NOT NULL,
    tags_json TEXT DEFAULT '[]',
    metadata_json TEXT DEFAULT '{}',
    supersedes_source_id TEXT DEFAULT '',
    immutable INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_kind ON raw_sources(source_kind);
CREATE INDEX IF NOT EXISTS idx_raw_origin ON raw_sources(origin);
CREATE INDEX IF NOT EXISTS idx_raw_symbol ON raw_sources(symbol);
CREATE INDEX IF NOT EXISTS idx_raw_trade_date ON raw_sources(trade_date);
CREATE INDEX IF NOT EXISTS idx_raw_published ON raw_sources(published_at);
CREATE INDEX IF NOT EXISTS idx_raw_captured ON raw_sources(captured_at);
CREATE INDEX IF NOT EXISTS idx_raw_source_ref ON raw_sources(source_ref);

CREATE TABLE IF NOT EXISTS raw_source_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    linked_source_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_links_source ON raw_source_links(source_id);
CREATE INDEX IF NOT EXISTS idx_raw_links_linked ON raw_source_links(linked_source_id);
"""


STOCK_ANALYSIS_PREFIXES = {
    "market_report": "01",
    "sentiment_report": "02",
    "news_report": "03",
    "fundamentals_report": "04",
    "catalyst_report": "05",
    "flow_risk_report": "06",
    "data_quality_summary": "08",
    "bull_bear_debate": "10",
    "trader_investment_plan": "20",
    "risk_debate": "30",
    "final_trade_decision": "31",
    "full_report": "99",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _safe_component(value: str, fallback: str = "unknown") -> str:
    clean = re.sub(r"[^0-9A-Za-z_\-.]+", "_", value.strip())
    return clean.strip("._") or fallback


def _date_from_iso(value: str, fallback: str = "") -> str:
    if value and len(value) >= 10:
        first10 = value[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", first10):
            return first10
    return fallback or datetime.now().strftime("%Y-%m-%d")


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RawStore:
    """Append-only raw source store.

    The markdown body is immutable. Metadata/frontmatter may be amended, but
    `content_sha256` always hashes only the body markdown, never frontmatter.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.knowledge_dir != Path("./data/knowledge"):
            if settings.raw_knowledge_dir == Path("./data/knowledge/raw"):
                settings.raw_knowledge_dir = settings.knowledge_dir / "raw"
            if settings.raw_knowledge_db_path == Path("./data/knowledge/raw/index.db"):
                settings.raw_knowledge_db_path = settings.raw_knowledge_dir / "index.db"
        self.base_dir = settings.raw_knowledge_dir
        self.db_path = settings.raw_knowledge_db_path
        self.sources_dir = self.base_dir / "sources"

    async def init_db(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "assets").mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(RAW_SCHEMA)
            await db.commit()

    async def add_source(
        self,
        *,
        source_kind: str,
        origin: str,
        title: str,
        markdown: str,
        metadata: dict,
    ) -> dict:
        if source_kind not in RAW_SOURCE_KINDS:
            raise ValueError(f"Unsupported raw source_kind: {source_kind}")
        if origin not in RAW_ORIGINS:
            raise ValueError(f"Unsupported raw origin: {origin}")
        if not title.strip():
            raise ValueError("Raw source title cannot be empty")
        if not markdown.strip():
            raise ValueError("Raw source markdown cannot be empty")

        await self.init_db()

        body = markdown.rstrip() + "\n"
        content_sha256 = _sha256_text(body)
        now = _now_iso()
        meta = dict(metadata or {})
        meta.setdefault("captured_at", now)
        captured_at = str(meta.get("captured_at") or now)

        canonical_uri = str(
            meta.get("canonical_uri")
            or meta.get("source_url")
            or meta.get("url")
            or meta.get("pdf_url")
            or ""
        ).strip()
        source_ref = str(meta.get("source_ref") or canonical_uri or "").strip()
        provider = str(meta.get("provider") or meta.get("source") or "").strip()
        symbols = _as_list(meta.get("symbols"))
        symbol = str(meta.get("symbol") or (symbols[0] if symbols else "")).strip()
        if symbol and symbol not in symbols:
            symbols.insert(0, symbol)
        trade_date = str(meta.get("trade_date") or "").strip()
        published_at = str(meta.get("published_at") or meta.get("time") or "").strip()
        occurred_at = str(meta.get("occurred_at") or "").strip()
        tags = _as_list(meta.get("tags"))
        supersedes_source_id = str(meta.get("supersedes_source_id") or "").strip()

        source_id = str(meta.get("source_id") or "").strip()
        if not source_id:
            source_id = self._generate_source_id(
                source_kind=source_kind,
                content_sha256=content_sha256,
                canonical_uri=canonical_uri,
                source_ref=source_ref,
                symbol=symbol,
                trade_date=trade_date,
                captured_at=captured_at,
                metadata=meta,
            )

        existing = await self.get_source_record(source_id)
        if existing:
            existing["duplicate"] = True
            return existing

        rel_path = self._build_relative_path(
            source_kind=source_kind,
            content_sha256=content_sha256,
            source_id=source_id,
            symbol=symbol,
            trade_date=trade_date,
            published_at=published_at,
            captured_at=captured_at,
            provider=provider,
            metadata=meta,
        )
        abs_path = self._resolve_raw_path(rel_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        core_frontmatter_keys = {
            "source_id",
            "source_kind",
            "origin",
            "title",
            "content_sha256",
            "canonical_uri",
            "source_ref",
            "provider",
            "symbol",
            "symbols",
            "trade_date",
            "published_at",
            "occurred_at",
            "captured_at",
            "tags",
            "supersedes_source_id",
        }
        frontmatter = {
            "source_id": source_id,
            "source_kind": source_kind,
            "origin": origin,
            "title": title.strip(),
            "content_sha256": content_sha256,
            "canonical_uri": canonical_uri,
            "source_ref": source_ref,
            "provider": provider,
            "symbol": symbol,
            "symbols": symbols,
            "trade_date": trade_date,
            "published_at": published_at,
            "occurred_at": occurred_at,
            "captured_at": captured_at,
            "tags": tags,
            "supersedes_source_id": supersedes_source_id,
            **{k: v for k, v in meta.items() if k not in core_frontmatter_keys},
        }
        text = f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{body}"

        await asyncio.to_thread(abs_path.write_text, text, encoding="utf-8", newline="\n")

        row = {
            "source_id": source_id,
            "source_kind": source_kind,
            "origin": origin,
            "title": title.strip(),
            "content_path": rel_path.as_posix(),
            "content_sha256": content_sha256,
            "canonical_uri": canonical_uri,
            "source_ref": source_ref,
            "provider": provider,
            "symbol": symbol,
            "symbols_json": _json_dumps(symbols),
            "trade_date": trade_date,
            "published_at": published_at,
            "occurred_at": occurred_at,
            "captured_at": captured_at,
            "tags_json": _json_dumps(tags),
            "metadata_json": _json_dumps(meta),
            "supersedes_source_id": supersedes_source_id,
            "immutable": 1,
            "created_at": now,
            "updated_at": now,
        }
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO raw_sources
                   (source_id, source_kind, origin, title, content_path, content_sha256,
                    canonical_uri, source_ref, provider, symbol, symbols_json, trade_date,
                    published_at, occurred_at, captured_at, tags_json, metadata_json,
                    supersedes_source_id, immutable, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(row[k] for k in (
                    "source_id",
                    "source_kind",
                    "origin",
                    "title",
                    "content_path",
                    "content_sha256",
                    "canonical_uri",
                    "source_ref",
                    "provider",
                    "symbol",
                    "symbols_json",
                    "trade_date",
                    "published_at",
                    "occurred_at",
                    "captured_at",
                    "tags_json",
                    "metadata_json",
                    "supersedes_source_id",
                    "immutable",
                    "created_at",
                    "updated_at",
                )),
            )
            await db.commit()

        return {**self._normalise_record(row), "duplicate": False}

    async def read_source(self, source_id: str) -> dict:
        row = await self.get_source_record(source_id)
        if not row:
            raise FileNotFoundError(source_id)
        abs_path = self._resolve_raw_path(Path(row["content_path"]))
        text = await asyncio.to_thread(abs_path.read_text, encoding="utf-8")
        row["content"] = text
        row["markdown"] = self._extract_body(text)
        row["frontmatter"] = self._extract_frontmatter(text)
        return row

    async def list_sources(
        self,
        *,
        source_kind: str | None = None,
        symbol: str | None = None,
        trade_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        await self.init_db()
        clauses: list[str] = []
        params: list[Any] = []
        if source_kind:
            clauses.append("source_kind = ?")
            params.append(source_kind)
        if symbol:
            clauses.append("(symbol = ? OR symbols_json LIKE ?)")
            params.extend([symbol, f"%{symbol}%"])
        if trade_date:
            clauses.append("trade_date = ?")
            params.append(trade_date)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            "SELECT * FROM raw_sources"
            + where
            + " ORDER BY captured_at DESC, created_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([max(1, min(limit, 200)), max(0, offset)])
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                return [self._normalise_record(dict(row)) for row in await cursor.fetchall()]

    async def update_source(
        self,
        source_id: str,
        *,
        title: str,
        markdown: str,
        metadata: dict | None = None,
    ) -> dict:
        source = await self.read_source(source_id)
        old_meta = dict(source.get("metadata") or {})
        old_tags = source.get("tags") or []
        next_meta = {**old_meta, **(metadata or {})}
        next_tags = old_tags
        updated_at = _now_iso()

        body = markdown.rstrip() + "\n"
        content_sha256 = _sha256_text(body)
        abs_path = self._resolve_raw_path(Path(source["content_path"]))

        frontmatter = dict(source.get("frontmatter") or {})
        frontmatter["title"] = title.strip()
        frontmatter["content_sha256"] = content_sha256
        frontmatter.update(next_meta)
        frontmatter["tags"] = next_tags
        frontmatter["updated_at"] = updated_at
        text = f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{body}"
        await asyncio.to_thread(abs_path.write_text, text, encoding="utf-8", newline="\n")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE raw_sources
                   SET title = ?, content_sha256 = ?, metadata_json = ?, updated_at = ?
                   WHERE source_id = ?""",
                (title.strip(), content_sha256, _json_dumps(next_meta), updated_at, source_id),
            )
            await db.commit()
        updated = await self.get_source_record(source_id)
        if not updated:
            raise FileNotFoundError(source_id)
        return updated

    async def update_metadata(
        self,
        source_id: str,
        *,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        source = await self.read_source(source_id)
        old_meta = dict(source.get("metadata") or {})
        old_tags = source.get("tags") or []
        next_meta = {**old_meta, **(metadata or {})}
        next_tags = old_tags if tags is None else tags
        updated_at = _now_iso()

        abs_path = self._resolve_raw_path(Path(source["content_path"]))
        frontmatter = dict(source.get("frontmatter") or {})
        frontmatter.update(next_meta)
        frontmatter["tags"] = next_tags
        frontmatter["updated_at"] = updated_at
        body = source.get("markdown", "")
        text = f"---\n{yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{body.rstrip()}\n"
        await asyncio.to_thread(abs_path.write_text, text, encoding="utf-8", newline="\n")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE raw_sources
                   SET tags_json = ?, metadata_json = ?, updated_at = ?
                   WHERE source_id = ?""",
                (_json_dumps(next_tags), _json_dumps(next_meta), updated_at, source_id),
            )
            await db.commit()
        updated = await self.get_source_record(source_id)
        if not updated:
            raise FileNotFoundError(source_id)
        return updated

    async def verify_source(self, source_id: str) -> bool:
        source = await self.read_source(source_id)
        actual = _sha256_text(source["markdown"].rstrip() + "\n")
        return actual == source["content_sha256"]

    async def get_source_record(self, source_id: str) -> dict | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM raw_sources WHERE source_id = ?",
                (source_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return self._normalise_record(dict(row)) if row else None

    async def find_by_source_ref(
        self,
        *,
        source_kind: str,
        source_ref: str,
        symbol: str = "",
    ) -> dict | None:
        if not source_ref:
            return None
        await self.init_db()
        sql = "SELECT * FROM raw_sources WHERE source_kind = ? AND source_ref = ?"
        params: list[Any] = [source_kind, source_ref]
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        sql += " LIMIT 1"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                row = await cursor.fetchone()
                return self._normalise_record(dict(row)) if row else None

    async def latest_for_trade_date(self, source_kind: str, trade_date: str) -> dict | None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM raw_sources
                   WHERE source_kind = ? AND trade_date = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (source_kind, trade_date),
            ) as cursor:
                row = await cursor.fetchone()
                return self._normalise_record(dict(row)) if row else None

    async def versions_for_trade_date(self, source_kind: str, trade_date: str) -> list[dict]:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM raw_sources
                   WHERE source_kind = ? AND trade_date = ?
                   ORDER BY created_at DESC""",
                (source_kind, trade_date),
            ) as cursor:
                return [self._normalise_record(dict(row)) for row in await cursor.fetchall()]

    async def add_link(
        self,
        source_id: str,
        linked_source_id: str,
        link_type: str,
    ) -> None:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO raw_source_links
                   (source_id, linked_source_id, link_type, created_at)
                   VALUES (?, ?, ?, ?)""",
                (source_id, linked_source_id, link_type, _now_iso()),
            )
            await db.commit()

    def _generate_source_id(
        self,
        *,
        source_kind: str,
        content_sha256: str,
        canonical_uri: str,
        source_ref: str,
        symbol: str,
        trade_date: str,
        captured_at: str,
        metadata: dict,
    ) -> str:
        if source_kind == "daily_direction":
            key = metadata.get("run_id") or f"daily_direction:{trade_date}:{content_sha256}"
        elif source_kind == "analysis_memory":
            key = metadata.get("run_id") or ":".join(
                [
                    "analysis_memory",
                    symbol,
                    trade_date,
                    str(metadata.get("linked_full_report_source_id") or content_sha256),
                ]
            )
        elif source_kind == "stock_analysis":
            key = ":".join(
                [
                    "stock_analysis",
                    symbol,
                    trade_date,
                    str(metadata.get("run_id") or content_sha256),
                    str(metadata.get("analysis_node") or ""),
                ]
            )
        elif source_kind in {"news_article", "announcement", "research_report"}:
            key = source_ref or ":".join(
                [
                    source_kind,
                    symbol,
                    str(metadata.get("title") or metadata.get("published_at") or ""),
                    content_sha256,
                ]
            )
        elif source_kind == "manual_source":
            key = f"manual_source:{content_sha256}"
        elif source_kind == "daily_trade_log":
            key = f"daily_trade_log:{trade_date}:{captured_at}:{content_sha256[:12]}"
        else:
            key = f"{source_kind}:{canonical_uri or content_sha256}"
        return f"{source_kind}:{_stable_hash(key)}"

    def _build_relative_path(
        self,
        *,
        source_kind: str,
        content_sha256: str,
        source_id: str,
        symbol: str,
        trade_date: str,
        published_at: str,
        captured_at: str,
        provider: str,
        metadata: dict,
    ) -> Path:
        captured_date = _date_from_iso(captured_at)
        date_part = trade_date or _date_from_iso(published_at, captured_date)
        hash8 = content_sha256[:8]
        id_hash = _stable_hash(source_id, 8)
        safe_provider = _safe_component(provider or "source")

        if source_kind == "daily_direction":
            run_time = str(metadata.get("run_time") or captured_at[11:19]).replace(":", "")
            return Path("sources") / source_kind / date_part / f"daily_direction_{date_part}_{run_time}_{id_hash}.md"

        if source_kind == "analysis_memory":
            safe_symbol = safe_ticker_component(symbol or "unknown")
            run_time = str(metadata.get("run_time") or captured_at[11:19]).replace(":", "")
            return Path("sources") / source_kind / safe_symbol / date_part / f"analysis_memory_{date_part}_{run_time}_{id_hash}.md"

        if source_kind == "stock_analysis":
            safe_symbol = safe_ticker_component(symbol or "unknown")
            node = _safe_component(str(metadata.get("analysis_node") or "report"))
            seq = STOCK_ANALYSIS_PREFIXES.get(node, "99")
            run_time = str(metadata.get("run_time") or captured_at[11:19]).replace(":", "")
            return Path("sources") / source_kind / safe_symbol / date_part / f"{seq}_{node}_{run_time}_{id_hash}.md"

        if source_kind == "news_article":
            safe_symbol = safe_ticker_component(symbol or "market")
            return Path("sources") / source_kind / safe_symbol / date_part / f"news_{safe_provider}_{hash8}.md"

        if source_kind == "announcement":
            safe_symbol = safe_ticker_component(symbol or "market")
            return Path("sources") / source_kind / safe_symbol / date_part / f"announcement_{safe_provider}_{hash8}.md"

        if source_kind == "research_report":
            safe_symbol = safe_ticker_component(symbol or "market")
            return Path("sources") / source_kind / safe_symbol / date_part / f"research_{safe_provider}_{hash8}.md"

        if source_kind == "manual_source":
            return Path("sources") / source_kind / date_part / f"manual_{hash8}.md"

        if source_kind == "daily_trade_log":
            month = date_part[:7]
            run_time = captured_at[11:19].replace(":", "")
            return Path("sources") / source_kind / month / f"{date_part}_{run_time}_{hash8}.md"

        return Path("sources") / source_kind / date_part / f"{source_kind}_{hash8}.md"

    def _resolve_raw_path(self, rel_path: Path) -> Path:
        raw_root = self.base_dir.resolve()
        abs_path = (self.base_dir / rel_path).resolve()
        try:
            abs_path.relative_to(raw_root)
        except ValueError as exc:
            raise ValueError(f"Raw path escapes raw root: {rel_path}") from exc
        return abs_path

    @staticmethod
    def _extract_body(text: str) -> str:
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                body = text[end + 4 :]
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
    def _normalise_record(row: dict) -> dict:
        result = dict(row)
        result["source_kind_label"] = label_for_source_kind(str(result.get("source_kind") or ""))
        for json_field, public_field, fallback in [
            ("symbols_json", "symbols", []),
            ("tags_json", "tags", []),
            ("metadata_json", "metadata", {}),
        ]:
            raw = result.get(json_field)
            try:
                result[public_field] = json.loads(raw) if raw else fallback
            except (TypeError, json.JSONDecodeError):
                result[public_field] = fallback
        return result
