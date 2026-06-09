from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite
import yaml

from src.config import Settings
from src.knowledge.wiki_store import WikiStore


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class WikiLintService:
    def __init__(
        self,
        wiki_store: WikiStore,
        raw_db_path: Path | None = None,
        *,
        contradiction_age_days: int = 14,
        stale_page_days: int = 30,
        min_page_body_chars: int = 20,
    ):
        self.wiki_store = wiki_store
        self.raw_db_path = raw_db_path
        self.contradiction_age_days = contradiction_age_days
        self.stale_page_days = stale_page_days
        self.min_page_body_chars = min_page_body_chars

    async def run(self) -> dict:
        issues: list[dict] = []
        summary: dict[str, Any] = {
            "pages": 0,
            "broken_links": 0,
            "uncited_claims": 0,
            "pending_sources": 0,
            "missing_frontmatter": 0,
            "missing_source_ids": 0,
            "orphan_pages": 0,
            "stale_contradictions": 0,
            "duplicate_claims": 0,
            "empty_pages": 0,
            "stale_pages": 0,
        }

        # Check base files first (before any method that may trigger init_db)
        index_path = self.wiki_store.base_dir / "index.md"
        if not index_path.exists():
            issues.append({
                "severity": "error",
                "kind": "missing_index",
                "page_id": "home:index",
                "message": "index.md 不存在",
            })

        log_path = self.wiki_store.base_dir / "log.md"
        if not log_path.exists():
            issues.append({
                "severity": "error",
                "kind": "missing_log",
                "page_id": "home:log",
                "message": "log.md 不存在",
            })

        # 1. Broken wikilinks
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT l.*, p.title as from_title
                   FROM wiki_page_links l
                   LEFT JOIN wiki_pages p ON p.page_id = l.to_page_id
                   WHERE p.page_id IS NULL"""
            ) as cursor:
                for row in await cursor.fetchall():
                    issues.append({
                        "severity": "warning",
                        "kind": "broken_link",
                        "page_id": row["from_page_id"],
                        "message": f"链接目标不存在: {row['to_page_id']}",
                    })
                    summary["broken_links"] += 1

        # 2. Orphan pages: active pages with no inbound links.
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT p.page_id, p.title
                   FROM wiki_pages p
                   LEFT JOIN wiki_page_links l ON l.to_page_id = p.page_id
                   WHERE l.id IS NULL
                     AND p.status = 'active'
                     AND p.page_type NOT IN ('home', 'log')"""
            ) as cursor:
                for row in await cursor.fetchall():
                    issues.append({
                        "severity": "warning",
                        "kind": "orphan_page",
                        "page_id": row["page_id"],
                        "message": f"页面没有任何入链: {row['title']}",
                    })
                    summary["orphan_pages"] += 1

        # 3. Missing frontmatter fields and file-backed page checks
        pages = await self.wiki_store.list_pages(limit=1000)
        summary["pages"] = len(pages)
        required_fields = {"page_id", "page_type", "title", "slug", "status", "review_status"}
        exempt_types = {"home", "log"}
        stale_cutoff = datetime.now().astimezone() - timedelta(days=self.stale_page_days)
        for page in pages:
            page_type = page.get("page_type")
            if page.get("page_type") in exempt_types:
                continue
            try:
                abs_path = self.wiki_store._resolve_wiki_path(Path(page["content_path"]))
                text = abs_path.read_text(encoding="utf-8")
                fm = self._extract_frontmatter(text)
                missing = required_fields - set(fm.keys())
                if missing:
                    issues.append({
                        "severity": "warning",
                        "kind": "missing_frontmatter",
                        "page_id": page["page_id"],
                        "message": f"frontmatter 缺少字段: {', '.join(missing)}",
                    })
                    summary["missing_frontmatter"] += 1

                body = self.wiki_store._extract_body(text).strip()
                if len(body) < self.min_page_body_chars:
                    issues.append({
                        "severity": "warning",
                        "kind": "empty_page",
                        "page_id": page["page_id"],
                        "message": f"页面正文过短，可能是空页面: {page['title']}",
                    })
                    summary["empty_pages"] += 1
            except Exception:
                issues.append({
                    "severity": "error",
                    "kind": "missing_file",
                    "page_id": page["page_id"],
                    "message": f"文件不存在: {page['content_path']}",
                })
                continue

            if page_type in {"stock_profile", "daily_direction"}:
                updated_at = self._parse_datetime(page.get("updated_at", ""))
                if updated_at and updated_at < stale_cutoff:
                    issues.append({
                        "severity": "info",
                        "kind": "stale_page",
                        "page_id": page["page_id"],
                        "message": f"{page_type} 页面超过 {self.stale_page_days} 天未更新: {page['title']}",
                    })
                    summary["stale_pages"] += 1

        # 4. Page source_ids reference non-existent raw sources
        if self.raw_db_path and self.raw_db_path.exists():
            for page in pages:
                for sid in page.get("source_ids", []):
                    async with aiosqlite.connect(self.raw_db_path) as db:
                        async with db.execute(
                            "SELECT 1 FROM raw_sources WHERE source_id = ?", (sid,)
                        ) as cursor:
                            if not await cursor.fetchone():
                                issues.append({
                                    "severity": "warning",
                                    "kind": "missing_source",
                                    "page_id": page["page_id"],
                                    "message": f"source_id 不存在于 raw: {sid}",
                                })
                                summary["missing_source_ids"] += 1

        # 5. Claims checks
        contradiction_cutoff = datetime.now().astimezone() - timedelta(
            days=self.contradiction_age_days
        )
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM wiki_claims WHERE source_ids_json = '[]' OR source_ids_json = ''"
            ) as cursor:
                for row in await cursor.fetchall():
                    issues.append({
                        "severity": "error",
                        "kind": "uncited_claim",
                        "page_id": row["claim_id"],
                        "message": f"claim 没有 source_id: {row['statement']}",
                    })
                    summary["uncited_claims"] += 1

            async with db.execute(
                "SELECT * FROM wiki_claims WHERE status = 'contradicted'"
            ) as cursor:
                for row in await cursor.fetchall():
                    updated_at = self._parse_datetime(row["updated_at"])
                    if updated_at and updated_at < contradiction_cutoff:
                        issues.append({
                            "severity": "warning",
                            "kind": "stale_contradiction",
                            "page_id": row["claim_id"],
                            "message": f"矛盾论断超过 {self.contradiction_age_days} 天未处理: {row['statement']}",
                        })
                        summary["stale_contradictions"] += 1

            async with db.execute(
                """SELECT LOWER(TRIM(statement)) AS normalized_statement,
                          statement,
                          COUNT(*) AS claim_count,
                          GROUP_CONCAT(claim_id) AS claim_ids
                   FROM wiki_claims
                   WHERE status = 'active'
                   GROUP BY normalized_statement
                   HAVING claim_count > 1"""
            ) as cursor:
                for row in await cursor.fetchall():
                    claim_ids = row["claim_ids"] or ""
                    issues.append({
                        "severity": "warning",
                        "kind": "duplicate_claim",
                        "page_id": claim_ids.split(",")[0] if claim_ids else "",
                        "message": f"存在 {row['claim_count']} 条重复 active 论断: {row['statement']}",
                    })
                    summary["duplicate_claims"] += 1

        # 6. Pending sources count
        pending = await self.wiki_store.list_source_states(status="pending", limit=1000)
        summary["pending_sources"] = len(pending)
        if len(pending) > 50:
            issues.append({
                "severity": "info",
                "kind": "pending_sources",
                "page_id": "",
                "message": f"有 {len(pending)} 个待处理 raw source",
            })

        status = "ok"
        if any(i["severity"] == "error" for i in issues):
            status = "error"
        elif any(i["severity"] == "warning" for i in issues):
            status = "warning"

        result = {
            "status": status,
            "checked_at": _now_iso(),
            "issues": issues,
            "summary": summary,
        }

        # Save latest lint result
        await self._save_latest(result)
        return result

    async def get_latest(self) -> dict | None:
        lint_path = self.wiki_store.base_dir / ".lint_latest.json"
        if not lint_path.exists():
            return None
        text = await __import__("asyncio").to_thread(lint_path.read_text, encoding="utf-8")
        return json.loads(text)

    async def _save_latest(self, result: dict) -> None:
        lint_path = self.wiki_store.base_dir / ".lint_latest.json"
        await __import__("asyncio").to_thread(
            lint_path.write_text,
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )

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
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.astimezone()
        return parsed
