import pytest

from src.knowledge.derived_build import DerivedBuilder
from src.knowledge.derived_lint import DerivedLint
from src.knowledge.derived_models import BUILD_MODE_APPLY, BUILD_MODE_REBUILD
from src.knowledge.derived_store import DerivedStore
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore


@pytest.mark.asyncio
async def test_lint_passes_after_clean_build(test_settings):
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
    await builder.run(BUILD_MODE_APPLY)

    linter = DerivedLint()
    linter.raw_store = raw
    linter.wiki_store = wiki
    linter.derived_store = builder.derived_store

    result = await linter.run()
    assert result["status"] == "ok"
    assert result["summary"]["documents"] >= 2
    assert result["summary"]["issues"] == 0


@pytest.mark.asyncio
async def test_lint_detects_missing_document(test_settings):
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

    # Do not build derived
    linter = DerivedLint()
    linter.raw_store = raw
    linter.wiki_store = wiki
    linter.derived_store = DerivedStore(test_settings)
    await linter.derived_store.init_db()

    result = await linter.run()
    assert result["status"] == "error"
    issue_kinds = {i["kind"] for i in result["issues"]}
    assert "missing_document" in issue_kinds


@pytest.mark.asyncio
async def test_lint_detects_stale_hash(test_settings):
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

    builder = DerivedBuilder()
    builder.raw_store = raw
    builder.wiki_store = wiki
    builder.derived_store = DerivedStore(test_settings)
    await builder.run(BUILD_MODE_APPLY)

    # Modify raw source without rebuilding derived
    source = await raw.read_source((await raw.list_sources())[0]["source_id"])
    await raw.update_source(
        source_id=source["source_id"],
        title="Modified",
        markdown="Modified content.",
        metadata={},
    )

    linter = DerivedLint()
    linter.raw_store = raw
    linter.wiki_store = wiki
    linter.derived_store = builder.derived_store

    result = await linter.run()
    assert result["status"] == "error"
    issue_kinds = {i["kind"] for i in result["issues"]}
    assert "stale_hash" in issue_kinds
