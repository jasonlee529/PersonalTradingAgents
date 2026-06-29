import pytest

from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore
from src.knowledge.wiki_ingestor import WikiIngestor
from src.knowledge.wiki_planner import LLMWikiPlanner


def _make_stores(test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    return raw_store, wiki_store


@pytest.mark.asyncio
async def test_apply_creates_stock_pages(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    source = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"manual_subtype": "note", "symbols": ["603738"]},
    )

    result = await ingestor.ingest_source(source["source_id"])
    assert result["status"] == "completed"

    pages = await wiki_store.list_pages()
    types = {p["page_type"] for p in pages}
    assert "source_digest" in types
    assert "stock_profile" in types
    assert "stock_timeline" in types


@pytest.mark.asyncio
async def test_apply_sets_source_state_processed(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    source = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"symbols": ["603738"]},
    )

    await ingestor.ingest_source(source["source_id"])
    state = await wiki_store.get_source_state(source["source_id"])
    assert state is not None
    assert state["wiki_status"] == "processed"


@pytest.mark.asyncio
async def test_reapply_skips_without_force(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    source = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"symbols": ["603738"]},
    )

    r1 = await ingestor.ingest_source(source["source_id"])
    assert r1["status"] == "completed"

    r2 = await ingestor.ingest_source(source["source_id"])
    assert r2["status"] == "skipped"

    r3 = await ingestor.ingest_source(source["source_id"], force=True)
    assert r3["status"] == "completed"


@pytest.mark.asyncio
async def test_daily_direction_creates_daily_page(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    source = await raw_store.add_source(
        source_kind="daily_direction",
        origin="agent",
        title="2026-06-05 今日方向",
        markdown="# 今日方向\n\n半导体",
        metadata={"trade_date": "2026-06-05", "run_id": "dir:2026-06-05:092027"},
    )

    result = await ingestor.ingest_source(source["source_id"])
    assert result["status"] == "completed"

    daily = await wiki_store.list_pages(page_type="daily_direction")
    assert len(daily) == 1
    assert daily[0]["page_id"] == "daily_direction:2026-06-05"


@pytest.mark.asyncio
async def test_daily_trade_log_creates_trade_month(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    source = await raw_store.add_source(
        source_kind="daily_trade_log",
        origin="user",
        title="2026-06-05 每日操作",
        markdown="# 操作\n\n买入 603738",
        metadata={"trade_date": "2026-06-05", "symbols": ["603738"]},
    )

    result = await ingestor.ingest_source(source["source_id"])
    assert result["status"] == "completed"

    months = await wiki_store.list_pages(page_type="trade_month")
    assert len(months) == 1
    assert months[0]["page_id"] == "trade_month:2026-06"


@pytest.mark.asyncio
async def test_analysis_run_ingest_groups_sources(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    run_id = "analysis:603738:2026-06-05:095641"
    s1 = await raw_store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 市场分析",
        markdown="# 市场分析\n\n...",
        metadata={"symbol": "603738", "trade_date": "2026-06-05", "run_id": run_id, "analysis_node": "market_report"},
    )
    s2 = await raw_store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 情绪分析",
        markdown="# 情绪分析\n\n...",
        metadata={"symbol": "603738", "trade_date": "2026-06-05", "run_id": run_id, "analysis_node": "sentiment_report"},
    )

    result = await ingestor.ingest_analysis_run(run_id)
    assert result["status"] == "completed"

    digests = await wiki_store.list_pages(page_type="analysis_run_digest")
    assert len(digests) == 1

    # Both sources should be marked processed
    for sid in [s1["source_id"], s2["source_id"]]:
        state = await wiki_store.get_source_state(sid)
        assert state["wiki_status"] == "processed"


@pytest.mark.asyncio
async def test_batch_ingest_processes_multiple_sources_in_one_run(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    s1 = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Batch Material 1",
        markdown="# Batch 1\n\nBody",
        metadata={"symbols": ["603738"]},
    )
    s2 = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Batch Material 2",
        markdown="# Batch 2\n\nBody",
        metadata={"symbols": ["603738"]},
    )

    result = await ingestor.ingest_batch([s1["source_id"], s2["source_id"]])

    assert result["status"] == "completed"
    assert result["batch_status"] == "completed"
    assert set(result["source_ids"]) == {s1["source_id"], s2["source_id"]}
    assert len({item["run_id"] for item in result["results"]}) == 1

    for sid in [s1["source_id"], s2["source_id"]]:
        state = await wiki_store.get_source_state(sid)
        assert state["wiki_status"] == "processed"
        assert state["latest_ingest_run_id"] == result["run_id"]

    pages = await wiki_store.list_pages()
    source_digests = [p for p in pages if p["page_type"] == "source_digest"]
    assert len(source_digests) == 2


@pytest.mark.asyncio
async def test_hash_mismatch_does_not_write(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store)

    source = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"symbols": ["603738"]},
    )

    # Tamper with file to break hash
    abs_path = test_settings.raw_knowledge_dir / source["content_path"]
    content = abs_path.read_text(encoding="utf-8")
    abs_path.write_text(content + "\ntampered", encoding="utf-8")

    result = await ingestor.ingest_source(source["source_id"])
    assert result["status"] == "failed"
    assert "hash" in result["warnings"][0].lower() or "mismatch" in result["warnings"][0].lower()


@pytest.mark.asyncio
async def test_failed_planner_run_does_not_write_pages(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()

    source = await raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"symbols": ["603738"]},
    )

    async def failing_invoke(prompt):
        raise ValueError("Simulated LLM failure")

    bad_planner = LLMWikiPlanner(test_settings, invoke_fn=failing_invoke)
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store, planner=bad_planner)

    with pytest.raises(ValueError) as exc_info:
        await ingestor.ingest_source(source["source_id"])
    assert "llm" in str(exc_info.value).lower() or "planner" in str(exc_info.value).lower() or "simulated" in str(exc_info.value).lower()

    # Verify no wiki pages were written (only home and log should exist)
    pages = await wiki_store.list_pages()
    types = {p["page_type"] for p in pages}
    assert "source_digest" not in types
    assert "stock_profile" not in types

    # Verify ingest run was recorded as failed
    runs = await wiki_store.list_source_states()
    # Actually list_source_states returns source states, not ingest runs.
    state = await wiki_store.get_source_state(source["source_id"])
    assert state["wiki_status"] == "failed"
    assert "Simulated LLM failure" in state["error"]

    # Check via DB directly for ingest run status
    import aiosqlite
    async with aiosqlite.connect(wiki_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM wiki_ingest_runs ORDER BY started_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["status"] == "failed"


@pytest.mark.asyncio
async def test_failed_analysis_run_marks_all_sources_failed(test_settings):
    raw_store, wiki_store = _make_stores(test_settings)
    await raw_store.init_db()
    await wiki_store.init_db()

    run_id = "analysis:603738:2026-06-05:095641"
    s1 = await raw_store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 市场分析",
        markdown="# 市场\n\n...",
        metadata={"symbol": "603738", "trade_date": "2026-06-05", "run_id": run_id, "analysis_node": "market_report"},
    )
    s2 = await raw_store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 情绪分析",
        markdown="# 情绪\n\n...",
        metadata={"symbol": "603738", "trade_date": "2026-06-05", "run_id": run_id, "analysis_node": "sentiment_report"},
    )

    async def failing_invoke(prompt):
        raise ValueError("Simulated analysis LLM failure")

    bad_planner = LLMWikiPlanner(test_settings, invoke_fn=failing_invoke)
    ingestor = WikiIngestor(test_settings, raw_store, wiki_store, planner=bad_planner)

    with pytest.raises(ValueError):
        await ingestor.ingest_analysis_run(run_id)

    for sid in [s1["source_id"], s2["source_id"]]:
        state = await wiki_store.get_source_state(sid)
        assert state["wiki_status"] == "failed"
        assert "Simulated analysis LLM failure" in state["error"]

    # Check via DB directly for ingest run status
    import aiosqlite
    async with aiosqlite.connect(wiki_store.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM wiki_ingest_runs ORDER BY started_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None
            assert row["status"] == "failed"
