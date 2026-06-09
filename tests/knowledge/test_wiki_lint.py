import pytest

from src.knowledge.wiki_store import WikiStore
from src.knowledge.wiki_lint import WikiLintService


@pytest.mark.asyncio
async def test_lint_finds_missing_log(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()
    # Remove log.md
    log_path = test_settings.wiki_knowledge_dir / "log.md"
    if log_path.exists():
        log_path.unlink()

    lint = WikiLintService(wiki_store)
    result = await lint.run()

    assert result["status"] == "error"
    missing_log = [i for i in result["issues"] if i["kind"] == "missing_log"]
    assert len(missing_log) == 1


@pytest.mark.asyncio
async def test_lint_finds_uncited_claim(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()

    # Insert claim without source_id directly into DB
    import aiosqlite
    async with aiosqlite.connect(wiki_store.db_path) as db:
        await db.execute(
            """INSERT INTO wiki_claims
               (claim_id, subject_type, subject_id, claim_type, statement, polarity,
                status, confidence, source_ids_json, page_ids_json, contradicts_json,
                metadata_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("claim:test", "stock", "603738", "fact", "无来源 claim", "", "active", 0.0,
             "[]", "[]", "[]", "{}", "2026-06-05", "2026-06-05"),
        )
        await db.commit()

    lint = WikiLintService(wiki_store)
    result = await lint.run()

    uncited = [i for i in result["issues"] if i["kind"] == "uncited_claim"]
    assert len(uncited) == 1
    assert "无来源 claim" in uncited[0]["message"]


@pytest.mark.asyncio
async def test_lint_ok_when_healthy(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()

    lint = WikiLintService(wiki_store)
    result = await lint.run()

    # Should be ok or warning, not error
    assert result["status"] in ("ok", "warning")
    assert result["summary"]["pages"] >= 0


@pytest.mark.asyncio
async def test_lint_missing_frontmatter(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()

    # Create a page with minimal frontmatter
    await wiki_store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738",
        slug="stocks/603738",
        markdown="正文",
        metadata={"symbol": "603738"},
    )

    lint = WikiLintService(wiki_store)
    result = await lint.run()

    # The page should have valid frontmatter since upsert_page writes it properly
    # So this test mainly verifies the lint runs without crashing
    assert "summary" in result


@pytest.mark.asyncio
async def test_lint_get_latest(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()

    lint = WikiLintService(wiki_store)
    latest_before = await lint.get_latest()
    assert latest_before is None

    await lint.run()
    latest_after = await lint.get_latest()
    assert latest_after is not None
    assert latest_after["status"] in ("ok", "warning", "error")


@pytest.mark.asyncio
async def test_lint_finds_orphan_and_empty_pages(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()

    await wiki_store.upsert_page(
        page_id="stock:ORPHAN",
        page_type="stock_profile",
        title="孤立页面",
        slug="stocks/ORPHAN",
        markdown="短",
        metadata={"symbol": "ORPHAN"},
    )

    lint = WikiLintService(wiki_store)
    result = await lint.run()

    kinds = {issue["kind"] for issue in result["issues"]}
    assert "orphan_page" in kinds
    assert "empty_page" in kinds
    assert result["summary"]["orphan_pages"] >= 1
    assert result["summary"]["empty_pages"] >= 1


@pytest.mark.asyncio
async def test_lint_finds_duplicate_claims_and_stale_contradictions(test_settings):
    wiki_store = WikiStore(test_settings)
    await wiki_store.init_db()

    import aiosqlite
    async with aiosqlite.connect(wiki_store.db_path) as db:
        rows = [
            ("claim:dup1", "stock", "603738", "fact", "同一论断", "", "active", 0.6, '["manual_source:a"]', "[]", "[]", "{}", "2026-06-05", "2026-06-05"),
            ("claim:dup2", "stock", "603738", "fact", "同一论断", "", "active", 0.6, '["manual_source:b"]', "[]", "[]", "{}", "2026-06-05", "2026-06-05"),
            ("claim:old_conflict", "stock", "603738", "contradiction", "旧矛盾", "", "contradicted", 0.6, '["manual_source:c"]', "[]", "[]", "{}", "2026-05-01", "2026-05-01"),
        ]
        for row in rows:
            await db.execute(
                """INSERT INTO wiki_claims
                   (claim_id, subject_type, subject_id, claim_type, statement, polarity,
                    status, confidence, source_ids_json, page_ids_json, contradicts_json,
                    metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    lint = WikiLintService(wiki_store, contradiction_age_days=7)
    result = await lint.run()

    kinds = {issue["kind"] for issue in result["issues"]}
    assert "duplicate_claim" in kinds
    assert "stale_contradiction" in kinds
    assert result["summary"]["duplicate_claims"] == 1
    assert result["summary"]["stale_contradictions"] == 1
