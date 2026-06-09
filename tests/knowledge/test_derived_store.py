from pathlib import Path

import pytest

from src.knowledge.derived_store import DerivedStore


@pytest.mark.asyncio
async def test_init_db_creates_tables(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()
    assert test_settings.derived_knowledge_db_path.exists()


@pytest.mark.asyncio
async def test_upsert_and_get_document(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    doc = await store.upsert_document({
        "doc_id": "raw:manual_source:test123",
        "doc_type": "raw_source",
        "source_id": "manual_source:test123",
        "title": "Test Source",
        "path": "sources/manual_source/test.md",
        "content_sha256": "abc123",
        "metadata": {"foo": "bar"},
    })
    assert doc["doc_id"] == "raw:manual_source:test123"

    fetched = await store.get_document("raw:manual_source:test123")
    assert fetched is not None
    assert fetched["title"] == "Test Source"


@pytest.mark.asyncio
async def test_replace_chunks(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    await store.upsert_document({
        "doc_id": "wiki:stock:603738",
        "doc_type": "wiki_page",
        "page_id": "stock:603738",
        "title": "603738",
        "path": "pages/stocks/603738.md",
        "content_sha256": "sha1",
    })

    chunks = [
        {
            "chunk_id": "wiki:stock:603738:c0",
            "doc_type": "wiki_page",
            "ordinal": 0,
            "heading_path": "# 摘要",
            "text": "摘要内容",
            "token_estimate": 10,
        },
        {
            "chunk_id": "wiki:stock:603738:c1",
            "doc_type": "wiki_page",
            "ordinal": 1,
            "heading_path": "# 风险",
            "text": "风险内容",
            "token_estimate": 8,
        },
    ]
    await store.replace_chunks("wiki:stock:603738", chunks)

    fetched = await store.list_chunks_for_doc("wiki:stock:603738")
    assert len(fetched) == 2
    assert fetched[0]["ordinal"] == 0
    assert fetched[1]["ordinal"] == 1

    # Replace should clear old chunks
    await store.replace_chunks("wiki:stock:603738", [chunks[0]])
    fetched2 = await store.list_chunks_for_doc("wiki:stock:603738")
    assert len(fetched2) == 1


@pytest.mark.asyncio
async def test_upsert_entity_and_mentions(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    await store.upsert_entity({
        "entity_id": "stock:603738",
        "entity_type": "stock",
        "name": "603738",
        "canonical_key": "603738",
    })

    ent = await store.get_entity("stock:603738")
    assert ent is not None
    assert ent["entity_type"] == "stock"

    await store.add_entity_mentions([
        {
            "entity_id": "stock:603738",
            "doc_id": "wiki:stock:603738",
            "chunk_id": "wiki:stock:603738:c0",
            "mention_text": "603738",
            "mention_type": "symbol",
        }
    ])


@pytest.mark.asyncio
async def test_build_run_lifecycle(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    run_id = await store.create_build_run("dry_run")
    assert run_id.startswith("build:")

    await store.complete_build_run(run_id, {
        "status": "completed",
        "documents_seen": 5,
        "documents_indexed": 5,
        "chunks_indexed": 12,
        "entities_indexed": 3,
    })

    latest = await store.get_latest_build_run()
    assert latest is not None
    assert latest["status"] == "completed"
    assert latest["documents_seen"] == 5


@pytest.mark.asyncio
async def test_fail_build_run(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    run_id = await store.create_build_run("apply")
    await store.fail_build_run(run_id, "disk full")

    latest = await store.get_latest_build_run()
    assert latest["status"] == "failed"
    assert "disk full" in latest["error"]


@pytest.mark.asyncio
async def test_clear(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    await store.upsert_document({
        "doc_id": "raw:test",
        "doc_type": "raw_source",
        "path": "test.md",
        "content_sha256": "sha",
    })
    await store.replace_chunks("raw:test", [
        {"chunk_id": "c1", "doc_type": "raw_source", "ordinal": 0, "text": "t"}
    ])

    await store.clear()
    stats = await store.stats()
    assert stats["derived_documents"] == 0
    assert stats["derived_chunks"] == 0


@pytest.mark.asyncio
async def test_path_security(test_settings):
    store = DerivedStore(test_settings)
    with pytest.raises(ValueError, match="escapes"):
        store._resolve_derived_path(Path("../outside.txt"))


@pytest.mark.asyncio
async def test_add_links_and_claim_refs(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    await store.add_links([
        {
            "from_type": "wiki_page",
            "from_id": "home:index",
            "to_type": "wiki_page",
            "to_id": "stock:603738",
            "link_type": "wikilink",
        }
    ])

    await store.add_claim_refs([
        {
            "claim_id": "claim:abc",
            "doc_id": "wiki:stock:603738",
            "source_id": "manual_source:test",
            "claim_type": "fact",
        }
    ])

    links = await store.list_links()
    assert len(links) == 1
    assert links[0]["from_id"] == "home:index"

    claims = await store.list_claim_refs()
    assert len(claims) == 1
    assert claims[0]["claim_id"] == "claim:abc"


@pytest.mark.asyncio
async def test_stats(test_settings):
    store = DerivedStore(test_settings)
    await store.init_db()

    stats = await store.stats()
    assert "derived_documents" in stats
    assert "derived_chunks" in stats
    assert "derived_entities" in stats
