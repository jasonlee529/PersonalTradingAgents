import pytest

from src.knowledge.raw_store import RawStore


@pytest.mark.asyncio
async def test_raw_store_add_read_verify_and_duplicate(test_settings):
    store = RawStore(test_settings)
    await store.init_db()

    first = await store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"manual_subtype": "note", "symbols": ["603738"], "tags": ["manual/note"]},
    )

    assert first["source_kind"] == "manual_source"
    assert first["duplicate"] is False
    assert (test_settings.raw_knowledge_dir / first["content_path"]).exists()

    source = await store.read_source(first["source_id"])
    assert source["markdown"].startswith("# 标题")
    assert source["frontmatter"]["source_id"] == first["source_id"]
    assert await store.verify_source(first["source_id"]) is True

    duplicate = await store.add_source(
        source_kind="manual_source",
        origin="user",
        title="测试材料",
        markdown="# 标题\n\n正文",
        metadata={"manual_subtype": "note", "symbols": ["603738"], "tags": ["manual/note"]},
    )
    assert duplicate["source_id"] == first["source_id"]
    assert duplicate["duplicate"] is True


@pytest.mark.asyncio
async def test_raw_store_list_and_metadata_update(test_settings):
    store = RawStore(test_settings)
    await store.init_db()
    source = await store.add_source(
        source_kind="news_article",
        origin="external",
        title="新闻",
        markdown="正文",
        metadata={
            "symbol": "603738",
            "trade_date": "2026-06-04",
            "provider": "eastmoney",
            "source_ref": "abc",
            "tags": ["stock/603738"],
        },
    )

    rows = await store.list_sources(source_kind="news_article", symbol="603738", trade_date="2026-06-04")
    assert len(rows) == 1
    assert rows[0]["source_id"] == source["source_id"]

    updated = await store.update_metadata(
        source["source_id"],
        tags=["stock/603738", "reviewed"],
        metadata={"review_status": "ok"},
    )
    assert "reviewed" in updated["tags"]
    assert updated["metadata"]["review_status"] == "ok"
    assert await store.verify_source(source["source_id"]) is True
