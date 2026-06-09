from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from src.config import settings
from src.knowledge.derived_chunker import chunk_markdown
from src.knowledge.derived_entities import (
    ENTITY_TYPE_STOCK,
    ENTITY_TYPE_TOPIC,
    ENTITY_TYPE_SOURCE_KIND,
    ENTITY_TYPE_CLAIM_TYPE,
    ENTITY_TYPE_DATE,
    extract_entities_from_claim,
    extract_entities_from_raw_source,
    extract_entities_from_wiki_page,
)
from src.knowledge.derived_models import (
    BUILD_MODE_APPLY,
    BUILD_MODE_DRY_RUN,
    BUILD_MODE_REBUILD,
    BUILD_STATUS_COMPLETED,
    BUILD_STATUS_FAILED,
)
from src.knowledge.derived_store import DerivedStore
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


class DerivedBuilder:
    def __init__(self):
        self.raw_store = RawStore(settings)
        self.wiki_store = WikiStore(settings)
        self.derived_store = DerivedStore(settings)

    async def run(self, mode: str) -> dict:
        await self.derived_store.init_db()

        run_id = await self.derived_store.create_build_run(mode)
        result = {
            "run_id": run_id,
            "mode": mode,
            "status": BUILD_STATUS_COMPLETED,
            "documents_seen": 0,
            "documents_indexed": 0,
            "chunks_indexed": 0,
            "entities_indexed": 0,
            "error": "",
        }

        try:
            if mode == BUILD_MODE_REBUILD:
                await self.derived_store.clear()

            # Load sources and pages
            raw_sources = await self.raw_store.list_sources(limit=10000)
            wiki_pages = await self.wiki_store.list_pages(limit=10000)

            result["documents_seen"] = len(raw_sources) + len(wiki_pages)

            if mode == BUILD_MODE_DRY_RUN:
                estimated_chunks = 0
                for source in raw_sources:
                    full_source = await self.raw_store.read_source(source["source_id"])
                    body = full_source.get("markdown", "")
                    chunks = chunk_markdown(body, doc_id=f"raw:{source['source_id']}", doc_type="raw_source")
                    estimated_chunks += len(chunks)
                for page in wiki_pages:
                    full_page = await self.wiki_store.read_page(page["page_id"])
                    body = full_page.get("markdown", "")
                    chunks = chunk_markdown(body, doc_id=f"wiki:{page['page_id']}", doc_type="wiki_page")
                    estimated_chunks += len(chunks)

                result["documents_indexed"] = result["documents_seen"]
                result["chunks_indexed"] = estimated_chunks
                await self.derived_store.complete_build_run(run_id, result)
                return result

            # Index raw sources
            for source in raw_sources:
                full_source = await self.raw_store.read_source(source["source_id"])
                await self._index_raw_source(full_source)
                result["documents_indexed"] += 1

            # Index wiki pages
            for page in wiki_pages:
                full_page = await self.wiki_store.read_page(page["page_id"])
                await self._index_wiki_page(full_page)
                result["documents_indexed"] += 1

            # Extract entities and links from wiki claims
            claims = await self._list_wiki_claims()
            for claim in claims:
                await self._index_claim(claim)

            # Build links from wiki tables
            await self._build_wiki_links()

            # Count chunks and entities
            stats = await self.derived_store.stats()
            result["chunks_indexed"] = stats.get("derived_chunks", 0)
            result["entities_indexed"] = stats.get("derived_entities", 0)

            # Write manifest
            await self._write_manifest(
                raw_source_count=len(raw_sources),
                wiki_page_count=len(wiki_pages),
                stats=stats,
            )

            await self.derived_store.complete_build_run(run_id, result)
        except Exception as exc:
            result["status"] = BUILD_STATUS_FAILED
            result["error"] = str(exc)
            await self.derived_store.fail_build_run(run_id, str(exc))
            raise

        return result

    async def _index_raw_source(self, source: dict) -> None:
        doc_id = f"raw:{source['source_id']}"
        doc = {
            "doc_id": doc_id,
            "doc_type": "raw_source",
            "source_id": source["source_id"],
            "title": source.get("title", ""),
            "path": source.get("content_path", ""),
            "content_sha256": source.get("content_sha256", ""),
            "metadata": {
                "source_kind": source.get("source_kind", ""),
                "origin": source.get("origin", ""),
                "symbol": source.get("symbol", ""),
                "trade_date": source.get("trade_date", ""),
            },
        }
        await self.derived_store.upsert_document(doc)

        # Chunks
        body = source.get("markdown", "")
        chunks = chunk_markdown(body, doc_id=doc_id, doc_type="raw_source", metadata=doc["metadata"])
        await self.derived_store.replace_chunks(doc_id, chunks)

        # Entities
        entities = extract_entities_from_raw_source(source)
        mentions = []
        for ent in entities:
            await self.derived_store.upsert_entity(ent)
            mentions.append({
                "entity_id": ent["entity_id"],
                "doc_id": doc_id,
                "mention_text": ent["name"],
                "mention_type": ent["entity_type"],
            })
        await self.derived_store.replace_entity_mentions(doc_id, mentions)

        # Supersedes link
        supersedes = source.get("supersedes_source_id", "")
        if supersedes:
            await self.derived_store.add_links([{
                "from_type": "raw_source",
                "from_id": source["source_id"],
                "to_type": "raw_source",
                "to_id": supersedes,
                "link_type": "supersedes",
            }])

    async def _index_wiki_page(self, page: dict) -> None:
        doc_id = f"wiki:{page['page_id']}"
        metadata = page.get("frontmatter") or page.get("metadata") or {}
        doc = {
            "doc_id": doc_id,
            "doc_type": "wiki_page",
            "page_id": page["page_id"],
            "title": page.get("title", ""),
            "path": page.get("content_path", ""),
            "content_sha256": page.get("content_sha256", ""),
            "metadata": {
                "page_type": page.get("page_type", ""),
                "symbol": metadata.get("symbol", ""),
                "topic": metadata.get("topic", ""),
                "trade_date": metadata.get("trade_date", ""),
            },
        }
        await self.derived_store.upsert_document(doc)

        # Chunks
        body = page.get("markdown", "")
        chunks = chunk_markdown(body, doc_id=doc_id, doc_type="wiki_page", metadata=doc["metadata"])
        await self.derived_store.replace_chunks(doc_id, chunks)

        # Entities
        entities = extract_entities_from_wiki_page(page)
        mentions = []
        for ent in entities:
            await self.derived_store.upsert_entity(ent)
            mentions.append({
                "entity_id": ent["entity_id"],
                "doc_id": doc_id,
                "mention_text": ent["name"],
                "mention_type": ent["entity_type"],
            })
        await self.derived_store.replace_entity_mentions(doc_id, mentions)

    async def _index_claim(self, claim: dict) -> None:
        entities = extract_entities_from_claim(claim)
        for ent in entities:
            await self.derived_store.upsert_entity(ent)

        # Claim refs
        refs = []
        for sid in claim.get("source_ids", []):
            refs.append({
                "claim_id": claim["claim_id"],
                "doc_id": f"raw:{sid}",
                "source_id": sid,
                "claim_type": claim.get("claim_type", ""),
                "status": claim.get("status", ""),
            })
        for pid in claim.get("page_ids", []):
            refs.append({
                "claim_id": claim["claim_id"],
                "doc_id": f"wiki:{pid}",
                "page_id": pid,
                "claim_type": claim.get("claim_type", ""),
                "status": claim.get("status", ""),
            })
        await self.derived_store.replace_claim_refs(claim["claim_id"], refs)

    async def _build_wiki_links(self) -> None:
        # Page links from wiki_page_links
        import aiosqlite
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM wiki_page_links") as cursor:
                rows = await cursor.fetchall()

        links = []
        for row in rows:
            links.append({
                "from_type": "wiki_page",
                "from_id": row["from_page_id"],
                "to_type": "wiki_page",
                "to_id": row["to_page_id"],
                "link_type": row["link_type"] if "link_type" in row.keys() else "wikilink",
            })

        # Page-source links from wiki_page_sources
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM wiki_page_sources") as cursor:
                rows = await cursor.fetchall()

        for row in rows:
            links.append({
                "from_type": "wiki_page",
                "from_id": row["page_id"],
                "to_type": "raw_source",
                "to_id": row["source_id"],
                "link_type": "evidence",
            })

        if links:
            await self.derived_store.clear_links()
            await self.derived_store.add_links(links)

    async def _list_wiki_claims(self) -> list[dict]:
        import aiosqlite
        async with aiosqlite.connect(self.wiki_store.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM wiki_claims") as cursor:
                rows = await cursor.fetchall()
                results = []
                for row in rows:
                    claim = dict(row)
                    for json_field, public_field, fallback in [
                        ("source_ids_json", "source_ids", []),
                        ("page_ids_json", "page_ids", []),
                        ("contradicts_json", "contradicts", []),
                        ("metadata_json", "metadata", {}),
                    ]:
                        raw = claim.get(json_field)
                        try:
                            claim[public_field] = json.loads(raw) if raw else fallback
                        except (TypeError, json.JSONDecodeError):
                            claim[public_field] = fallback
                    results.append(claim)
                return results

    async def _write_manifest(self, *, raw_source_count: int, wiki_page_count: int, stats: dict) -> None:
        manifest = {
            "built_at": _now_iso(),
            "builder_version": "1.0.0",
            "raw_source_count": raw_source_count,
            "wiki_page_count": wiki_page_count,
            "document_count": stats.get("derived_documents", 0),
            "chunk_count": stats.get("derived_chunks", 0),
            "entity_count": stats.get("derived_entities", 0),
            "claim_ref_count": stats.get("derived_claim_refs", 0),
            "link_count": stats.get("derived_links", 0),
        }
        manifest_path = self.derived_store.settings.derived_knowledge_dir / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            manifest_path.write_text,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )


async def main():
    parser = argparse.ArgumentParser(description="Build derived knowledge index")
    parser.add_argument("--dry-run", action="store_true", help="Estimate without writing")
    parser.add_argument("--apply", action="store_true", help="Build or update derived")
    parser.add_argument("--rebuild", action="store_true", help="Clear and rebuild derived")
    args = parser.parse_args()

    mode = BUILD_MODE_DRY_RUN
    if args.rebuild:
        mode = BUILD_MODE_REBUILD
    elif args.apply:
        mode = BUILD_MODE_APPLY

    builder = DerivedBuilder()
    result = await builder.run(mode)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
