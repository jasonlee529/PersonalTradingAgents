from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.knowledge.derived_store import DerivedStore
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class DerivedLint:
    def __init__(self):
        self.derived_store = DerivedStore(settings)
        self.raw_store = RawStore(settings)
        self.wiki_store = WikiStore(settings)

    async def run(self) -> dict:
        issues: list[dict] = []

        # 1. derived DB exists
        if not self.derived_store.db_path.exists():
            issues.append({"severity": "error", "kind": "missing_db", "message": "derived/index.db not found"})

        # 2. manifest exists
        manifest_path = self.derived_store.base_dir / "manifest.json"
        if not manifest_path.exists():
            issues.append({"severity": "error", "kind": "missing_manifest", "message": "derived/manifest.json not found"})

        stats = await self.derived_store.stats()

        # 3. Every raw source has a derived document
        raw_sources = await self.raw_store.list_sources(limit=10000)
        raw_doc_ids = {f"raw:{s['source_id']}" for s in raw_sources}
        derived_docs = await self.derived_store.list_documents()
        derived_doc_ids = {d["doc_id"] for d in derived_docs}

        for sid in raw_doc_ids:
            if sid not in derived_doc_ids:
                issues.append({"severity": "error", "kind": "missing_document", "message": f"Raw source missing derived doc: {sid}"})

        # 4. Every wiki page has a derived document
        wiki_pages = await self.wiki_store.list_pages(limit=10000)
        wiki_doc_ids = {f"wiki:{p['page_id']}" for p in wiki_pages}
        for wid in wiki_doc_ids:
            if wid not in derived_doc_ids:
                issues.append({"severity": "error", "kind": "missing_document", "message": f"Wiki page missing derived doc: {wid}"})

        # 5. Non-empty docs have at least one chunk
        for doc in derived_docs:
            doc_id = doc["doc_id"]
            chunks = await self.derived_store.list_chunks_for_doc(doc_id)
            if not chunks:
                # Only require chunks if the original content is non-empty
                issues.append({"severity": "warning", "kind": "missing_chunks", "message": f"Document has no chunks: {doc_id}"})

        # 6. Document hash consistency
        for doc in derived_docs:
            doc_id = doc["doc_id"]
            doc_type = doc["doc_type"]
            derived_hash = doc["content_sha256"]
            if doc_type == "raw_source":
                source_id = doc["source_id"]
                source = await self.raw_store.get_source_record(source_id)
                if source and source.get("content_sha256") != derived_hash:
                    issues.append({"severity": "error", "kind": "stale_hash", "message": f"Derived hash stale for raw source: {source_id}"})
            elif doc_type == "wiki_page":
                page_id = doc["page_id"]
                page = await self.wiki_store._get_page_record(page_id)
                if page and page.get("content_sha256") != derived_hash:
                    issues.append({"severity": "error", "kind": "stale_hash", "message": f"Derived hash stale for wiki page: {page_id}"})

        # 7. All chunks point to existing documents (orphan chunk detection)
        import aiosqlite
        async with aiosqlite.connect(self.derived_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT chunk_id, doc_id FROM derived_chunks") as cursor:
                all_chunks = [dict(row) for row in await cursor.fetchall()]
        for chunk in all_chunks:
            if chunk["doc_id"] not in derived_doc_ids:
                issues.append({"severity": "error", "kind": "orphan_chunk", "message": f"Chunk {chunk['chunk_id']} points to missing doc: {chunk['doc_id']}"})

        # 8. Entity mentions point to existing documents
        async with aiosqlite.connect(self.derived_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM derived_entity_mentions") as cursor:
                mentions = [dict(row) for row in await cursor.fetchall()]
        for m in mentions:
            if m["doc_id"] not in derived_doc_ids:
                issues.append({"severity": "error", "kind": "orphan_mention", "message": f"Mention points to missing doc: {m['doc_id']}"})

        # 9. Claim refs point to existing documents and valid claims
        async with aiosqlite.connect(self.derived_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM derived_claim_refs") as cursor:
                claim_refs = [dict(row) for row in await cursor.fetchall()]
        for ref in claim_refs:
            if ref["doc_id"] not in derived_doc_ids:
                issues.append({"severity": "error", "kind": "orphan_claim_ref", "message": f"Claim ref points to missing doc: {ref['doc_id']}"})

        # 9b. All wiki claims have corresponding derived claim refs
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT claim_id FROM wiki_claims") as cursor:
                wiki_claims = [dict(row) for row in await cursor.fetchall()]
        wiki_claim_ids = {c["claim_id"] for c in wiki_claims}
        derived_claim_ids = {ref["claim_id"] for ref in claim_refs}
        for claim_id in wiki_claim_ids:
            if claim_id not in derived_claim_ids:
                issues.append({"severity": "error", "kind": "missing_claim_ref", "message": f"Wiki claim has no derived ref: {claim_id}"})

        # 9c. All derived claim refs point to valid wiki claims
        for ref in claim_refs:
            if ref["claim_id"] not in wiki_claim_ids:
                issues.append({"severity": "error", "kind": "invalid_claim_ref", "message": f"Claim ref points to missing claim: {ref['claim_id']}"})

        # 10. Latest build run is completed
        latest_run = await self.derived_store.get_latest_build_run()
        if not latest_run:
            issues.append({"severity": "warning", "kind": "no_build_run", "message": "No derived build run found"})
        elif latest_run.get("status") != "completed":
            issues.append({"severity": "error", "kind": "failed_build", "message": f"Latest build run failed: {latest_run.get('error', '')}"})

        status = "ok" if not issues else ("error" if any(i["severity"] == "error" for i in issues) else "warning")

        return {
            "status": status,
            "checked_at": _now_iso(),
            "summary": {
                "documents": stats.get("derived_documents", 0),
                "chunks": stats.get("derived_chunks", 0),
                "entities": stats.get("derived_entities", 0),
                "issues": len(issues),
            },
            "issues": issues,
        }


async def main():
    parser = argparse.ArgumentParser(description="Lint derived knowledge index")
    args = parser.parse_args()

    linter = DerivedLint()
    result = await linter.run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
