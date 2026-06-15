import pytest
import aiosqlite

from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_ingest_queue import MAX_RUNNING_WIKI_INGEST_SOURCES, WikiIngestQueue
from src.knowledge.wiki_store import WikiStore


def test_default_running_limit_is_ten():
    assert MAX_RUNNING_WIKI_INGEST_SOURCES == 10


@pytest.mark.asyncio
async def test_recover_interrupted_releases_running_source_state(test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()

    source = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Interrupted Source",
        markdown="# Interrupted\n\nBody",
        metadata={"symbols": ["603738"]},
    )
    run_id = "wiki_ingest:2026-06-06:120000000000:interrupted"
    async with aiosqlite.connect(wiki_store.db_path) as db:
        await db.execute(
            """INSERT INTO wiki_ingest_runs
               (run_id, trigger_type, source_id, raw_run_id, source_kind, status, mode, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                "source",
                source["source_id"],
                "",
                source["source_kind"],
                "applying",
                "apply",
                "2026-06-06T12:00:00",
            ),
        )
        await db.commit()
    await wiki_store.upsert_source_state(
        source_id=source["source_id"],
        source_kind=source["source_kind"],
        raw_content_sha256=source["content_sha256"],
        wiki_status="applying",
        latest_ingest_run_id=run_id,
    )

    queue = WikiIngestQueue(test_settings, raw_store, wiki_store)
    recovered = await queue.recover_interrupted()

    assert recovered == 1
    state = await wiki_store.get_source_state(source["source_id"])
    assert state["wiki_status"] == "failed"
    assert "interrupted" in state["error"].lower()

    async with aiosqlite.connect(wiki_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status, error FROM wiki_ingest_runs WHERE run_id = ?",
            (run_id,),
        ) as cursor:
            row = await cursor.fetchone()
    assert row["status"] == "failed"
    assert "interrupted" in row["error"].lower()


@pytest.mark.asyncio
async def test_enqueue_batch_creates_one_batch_run(test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()

    sources = []
    for idx in range(3):
        sources.append(await raw_store.add_source(
            source_kind="manual_source",
            origin="user",
            title=f"Batch Source {idx}",
            markdown=f"# Batch {idx}\n\nBody",
            metadata={"symbols": ["603738"]},
        ))

    queue = WikiIngestQueue(test_settings, raw_store, wiki_store)
    result = await queue.enqueue_batch([s["source_id"] for s in sources])

    assert result["batch_status"] == "queued"
    assert result["run_id"]
    assert queue._items.qsize() == 1

    async with aiosqlite.connect(wiki_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT trigger_type, status FROM wiki_ingest_runs") as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["trigger_type"] == "batch"
            assert rows[0]["status"] == "queued"

    for source in sources:
        state = await wiki_store.get_source_state(source["source_id"])
        assert state["wiki_status"] == "queued"
        assert state["latest_ingest_run_id"] == result["run_id"]
