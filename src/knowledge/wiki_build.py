from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from src.config import Settings
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore
from src.knowledge.wiki_ingestor import WikiIngestor
from src.knowledge.wiki_schema import WikiSchema


async def run_dry_run(settings: Settings) -> dict:
    raw_store = RawStore(settings)
    wiki_store = WikiStore(settings)
    await raw_store.init_db()
    await wiki_store.init_db()

    all_sources = await raw_store.list_sources(limit=1000)
    states = await wiki_store.list_source_states(limit=1000)
    state_map = {s["source_id"]: s for s in states}

    pending = [s for s in all_sources if not state_map.get(s["source_id"]) or state_map[s["source_id"]].get("wiki_status") in ("pending", "failed", "needs_reprocess")]

    by_kind: dict[str, int] = {}
    for s in pending:
        kind = s.get("source_kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1

    analysis_runs: dict[str, list] = {}
    for s in all_sources:
        if s.get("source_kind") == "stock_analysis":
            run_id = s.get("metadata", {}).get("run_id", "")
            if run_id:
                analysis_runs.setdefault(run_id, []).append(s)

    return {
        "total_raw_sources": len(all_sources),
        "pending_sources": len(pending),
        "by_kind": by_kind,
        "analysis_run_count": len(analysis_runs),
    }


async def run_apply(settings: Settings, limit: int = 100) -> dict:
    raw_store = RawStore(settings)
    wiki_store = WikiStore(settings)
    schema = WikiSchema(settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    await schema.ensure_schema()

    ingestor = WikiIngestor(settings, raw_store, wiki_store, schema)

    all_sources = await raw_store.list_sources(limit=1000)
    states = await wiki_store.list_source_states(limit=1000)
    state_map = {s["source_id"]: s for s in states}

    pending = [s for s in all_sources if not state_map.get(s["source_id"]) or state_map[s["source_id"]].get("wiki_status") in ("pending", "failed", "needs_reprocess")]

    # Group stock_analysis by run_id
    analysis_run_sources: dict[str, list] = {}
    other_sources: list = []
    for s in pending[:limit]:
        if s.get("source_kind") == "stock_analysis":
            run_id = s.get("metadata", {}).get("run_id", "")
            if run_id:
                analysis_run_sources.setdefault(run_id, []).append(s)
            else:
                other_sources.append(s)
        else:
            other_sources.append(s)

    results = []

    # Process analysis runs first
    for run_id, sources in list(analysis_run_sources.items())[:limit]:
        result = await ingestor.ingest_analysis_run(run_id)
        results.append({"type": "analysis_run", "run_id": run_id, "result": result})

    # Process other sources
    for s in other_sources:
        if len(results) >= limit:
            break
        result = await ingestor.ingest_source(s["source_id"])
        results.append({"type": "source", "source_id": s["source_id"], "result": result})

    completed = sum(1 for r in results if r["result"].get("status") == "completed")
    skipped = sum(1 for r in results if r["result"].get("status") == "skipped")
    failed = sum(1 for r in results if r["result"].get("status") == "failed")

    return {
        "processed": len(results),
        "completed": completed,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Wiki build CLI")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without writing")
    parser.add_argument("--apply", action="store_true", help="Apply ingest to pending sources")
    parser.add_argument("--limit", type=int, default=100, help="Max sources to process")
    args = parser.parse_args()

    settings = Settings()
    settings.ensure_dirs()

    if args.dry_run:
        result = asyncio.run(run_dry_run(settings))
        print(f"Total raw sources: {result['total_raw_sources']}")
        print(f"Pending sources: {result['pending_sources']}")
        print("By kind:")
        for kind, count in result["by_kind"].items():
            print(f"  {kind}: {count}")
        print(f"Analysis runs: {result['analysis_run_count']}")
        return 0

    if args.apply:
        result = asyncio.run(run_apply(settings, limit=args.limit))
        print(f"Processed: {result['processed']}")
        print(f"Completed: {result['completed']}")
        print(f"Skipped: {result['skipped']}")
        print(f"Failed: {result['failed']}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
