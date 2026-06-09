import pytest

from src.knowledge.derived_build import DerivedBuilder
from src.knowledge.derived_models import BUILD_MODE_APPLY, BUILD_MODE_DRY_RUN, BUILD_MODE_REBUILD
from src.knowledge.derived_store import DerivedStore
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore


@pytest.fixture
async def seeded_stores(test_settings):
    raw = RawStore(test_settings)
    wiki = WikiStore(test_settings)
    derived = DerivedStore(test_settings)
    await raw.init_db()
    await wiki.init_db()
    await derived.init_db()

    # Add a raw source
    await raw.add_source(
        source_kind="manual_source",
        origin="user",
        title="Test Source",
        markdown="# Test\n\nContent about 603738 on 2026-06-05.",
        metadata={"symbol": "603738", "tags": ["topic/test"]},
    )

    # Add a wiki page
    await wiki.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="# 603738\n\nTest content.",
        metadata={"symbol": "603738", "tags": ["topic/semiconductor"]},
    )

    return raw, wiki, derived


@pytest.mark.asyncio
async def test_dry_run_does_not_write(test_settings):
    builder = DerivedBuilder()
    builder.raw_store = RawStore(test_settings)
    builder.wiki_store = WikiStore(test_settings)
    builder.derived_store = DerivedStore(test_settings)

    await builder.raw_store.init_db()
    await builder.wiki_store.init_db()
    await builder.derived_store.init_db()

    # Add a raw source
    await builder.raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Test Source",
        markdown="# Test\n\nContent.",
        metadata={},
    )

    result = await builder.run(BUILD_MODE_DRY_RUN)
    assert result["mode"] == "dry_run"
    assert result["documents_seen"] >= 1

    stats = await builder.derived_store.stats()
    assert stats["derived_documents"] == 0


@pytest.mark.asyncio
async def test_apply_creates_documents_and_chunks(test_settings):
    raw = RawStore(test_settings)
    wiki = WikiStore(test_settings)
    await raw.init_db()
    await wiki.init_db()

    await raw.add_source(
        source_kind="manual_source",
        origin="user",
        title="Test Source",
        markdown="# Test\n\nContent about 603738.",
        metadata={"symbol": "603738"},
    )
    await wiki.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738",
        slug="stocks/603738",
        markdown="# 603738\n\nTest.",
        metadata={"symbol": "603738"},
    )

    builder = DerivedBuilder()
    builder.raw_store = raw
    builder.wiki_store = wiki
    builder.derived_store = DerivedStore(test_settings)

    result = await builder.run(BUILD_MODE_APPLY)
    assert result["status"] == "completed"
    assert result["documents_indexed"] >= 2

    stats = await builder.derived_store.stats()
    assert stats["derived_documents"] >= 2
    assert stats["derived_chunks"] >= 2


@pytest.mark.asyncio
async def test_rebuild_clears_and_rebuilds(test_settings):
    raw = RawStore(test_settings)
    wiki = WikiStore(test_settings)
    await raw.init_db()
    await wiki.init_db()

    await raw.add_source(
        source_kind="manual_source",
        origin="user",
        title="Test Source",
        markdown="# Test\n\nContent.",
        metadata={},
    )
    await wiki.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738",
        slug="stocks/603738",
        markdown="# 603738\n\nTest.",
        metadata={},
    )

    builder = DerivedBuilder()
    builder.raw_store = raw
    builder.wiki_store = wiki
    builder.derived_store = DerivedStore(test_settings)

    # First apply
    await builder.run(BUILD_MODE_APPLY)
    stats1 = await builder.derived_store.stats()
    assert stats1["derived_documents"] >= 2

    # Rebuild
    result = await builder.run(BUILD_MODE_REBUILD)
    assert result["status"] == "completed"

    stats2 = await builder.derived_store.stats()
    assert stats2["derived_documents"] >= 2


@pytest.mark.asyncio
async def test_manifest_written(test_settings):
    raw = RawStore(test_settings)
    wiki = WikiStore(test_settings)
    await raw.init_db()
    await wiki.init_db()

    await raw.add_source(
        source_kind="manual_source",
        origin="user",
        title="Test Source",
        markdown="正文",
        metadata={},
    )
    await wiki.upsert_page(
        page_id="home:index",
        page_type="home",
        title="Index",
        slug="index",
        markdown="# Index\n\nTest.",
        metadata={},
    )

    builder = DerivedBuilder()
    builder.raw_store = raw
    builder.wiki_store = wiki
    builder.derived_store = DerivedStore(test_settings)

    await builder.run(BUILD_MODE_APPLY)
    manifest_path = test_settings.derived_knowledge_dir / "manifest.json"
    assert manifest_path.exists()
