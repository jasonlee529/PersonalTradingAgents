import pytest

from src.knowledge.wiki_store import WikiStore


@pytest.mark.asyncio
async def test_init_db_creates_index_and_log(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    assert test_settings.wiki_knowledge_db_path.exists()
    assert (test_settings.wiki_knowledge_dir / "index.md").exists()
    assert (test_settings.wiki_knowledge_dir / "log.md").exists()

    # DB rows for base pages
    home = await store.read_page("home:index")
    assert home["page_type"] == "home"
    assert home["title"] == "PersonalTradingAgents Wiki"
    assert home["slug"] == "index"

    log = await store.read_page("home:log")
    assert log["page_type"] == "log"
    assert log["title"] == "Wiki Log"
    assert log["slug"] == "log"

    assert await store.verify_page("home:index") is True
    assert await store.verify_page("home:log") is True


@pytest.mark.asyncio
async def test_upsert_and_read_page(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    page = await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="# 603738 泰晶科技\n\n测试正文",
        metadata={"symbol": "603738", "tags": ["stock/603738"]},
    )

    assert page["page_id"] == "stock:603738"
    assert page["page_type"] == "stock_profile"

    read = await store.read_page("stock:603738")
    assert read["markdown"].startswith("# 603738")
    assert read["frontmatter"]["page_id"] == "stock:603738"
    assert read["frontmatter"]["slug"] == "stocks/603738"


@pytest.mark.asyncio
async def test_upsert_page_dedupes_slug_conflict(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    first = await store.upsert_page(
        page_id="source_digest:first",
        page_type="source_digest",
        title="First",
        slug="sources/manual/shared",
        markdown="# First",
        metadata={"source_id": "manual_source:first", "source_kind": "manual_source"},
    )
    second = await store.upsert_page(
        page_id="source_digest:second",
        page_type="source_digest",
        title="Second",
        slug="sources/manual/shared",
        markdown="# Second",
        metadata={"source_id": "manual_source:second", "source_kind": "manual_source"},
    )

    assert first["slug"] == "sources/manual/shared"
    assert second["slug"].startswith("sources/manual/shared-")
    assert second["slug"] != first["slug"]


@pytest.mark.asyncio
async def test_verify_page(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="# 603738 泰晶科技\n\n测试正文",
        metadata={"symbol": "603738"},
    )

    assert await store.verify_page("stock:603738") is True


@pytest.mark.asyncio
async def test_list_pages_filter(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="正文",
        metadata={"symbol": "603738"},
    )
    await store.upsert_page(
        page_id="stock:000001",
        page_type="stock_profile",
        title="000001 平安银行",
        slug="stocks/000001",
        markdown="正文",
        metadata={"symbol": "000001"},
    )
    await store.upsert_page(
        page_id="topic:ai",
        page_type="topic",
        title="AI 算力",
        slug="topics/ai",
        markdown="正文",
        metadata={"topic": "ai"},
    )

    stocks = await store.list_pages(page_type="stock_profile")
    assert len(stocks) == 2

    filtered = await store.list_pages(symbol="603738")
    assert len(filtered) == 1
    assert filtered[0]["page_id"] == "stock:603738"

    topics = await store.list_pages(page_type="topic")
    assert len(topics) == 1


@pytest.mark.asyncio
async def test_patch_section_replace(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown=(
            "# 603738 泰晶科技\n\n"
            "<!-- wiki-section:start:summary -->\n"
            "旧摘要\n"
            "<!-- wiki-section:end:summary -->\n\n"
            "<!-- wiki-section:start:position -->\n"
            "持仓\n"
            "<!-- wiki-section:end:position -->"
        ),
        metadata={"symbol": "603738"},
    )

    await store.patch_section(
        "stock:603738",
        section_id="summary",
        markdown="新摘要内容",
        mode="replace",
    )

    read = await store.read_page("stock:603738")
    assert "新摘要内容" in read["markdown"]
    assert "旧摘要" not in read["markdown"]
    assert "持仓" in read["markdown"]


@pytest.mark.asyncio
async def test_patch_section_append_and_prepend(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown=(
            "<!-- wiki-section:start:summary -->\n"
            "第一行\n"
            "<!-- wiki-section:end:summary -->"
        ),
        metadata={"symbol": "603738"},
    )

    await store.patch_section("stock:603738", section_id="summary", markdown="第二行", mode="append")
    read = await store.read_page("stock:603738")
    assert "第一行" in read["markdown"]
    assert "第二行" in read["markdown"]

    await store.patch_section("stock:603738", section_id="summary", markdown="第零行", mode="prepend")
    read2 = await store.read_page("stock:603738")
    lines = [l for l in read2["markdown"].splitlines() if l.strip() and not l.startswith("<")]
    assert lines[0] == "第零行"


@pytest.mark.asyncio
async def test_rebuild_page_links(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="# 603738\n\n参见 [[topics/ai|AI 算力]]",
        metadata={"symbol": "603738"},
    )
    await store.upsert_page(
        page_id="topic:ai",
        page_type="topic",
        title="AI 算力",
        slug="topics/ai",
        markdown="AI 主题",
        metadata={"topic": "ai"},
    )

    await store.rebuild_page_links("stock:603738")

    async with __import__("aiosqlite").connect(store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM wiki_page_links WHERE from_page_id = ?", ("stock:603738",)
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["to_page_id"] == "topic:ai"
            assert rows[0]["link_text"] == "AI 算力"


@pytest.mark.asyncio
async def test_link_page_source(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="正文",
        metadata={"symbol": "603738", "source_ids": ["manual_source:abc123"]},
    )

    async with __import__("aiosqlite").connect(store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM wiki_page_sources WHERE page_id = ?", ("stock:603738",)
        ) as cursor:
            rows = await cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["source_id"] == "manual_source:abc123"


@pytest.mark.asyncio
async def test_upsert_claim_requires_source_id(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    with pytest.raises(ValueError, match="source_id"):
        await store.upsert_claim({
            "subject_type": "stock",
            "subject_id": "603738",
            "claim_type": "fact",
            "statement": "测试 claim",
        })


@pytest.mark.asyncio
async def test_upsert_claim_ok(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    result = await store.upsert_claim({
        "subject_type": "stock",
        "subject_id": "603738",
        "claim_type": "fact",
        "statement": "测试 claim",
        "source_ids": ["manual_source:abc123"],
    })

    assert result["subject_id"] == "603738"
    assert result["statement"] == "测试 claim"
    assert "claim:" in result["claim_id"]


@pytest.mark.asyncio
async def test_source_state_crud(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    state = await store.upsert_source_state(
        source_id="manual_source:abc123",
        source_kind="manual_source",
        raw_content_sha256="sha256abc",
        wiki_status="pending",
    )
    assert state["wiki_status"] == "pending"
    assert state["page_ids"] == []

    read = await store.get_source_state("manual_source:abc123")
    assert read is not None
    assert read["source_id"] == "manual_source:abc123"

    await store.upsert_source_state(
        source_id="manual_source:abc123",
        source_kind="manual_source",
        raw_content_sha256="sha256abc",
        wiki_status="processed",
        page_ids=["stock:603738"],
    )

    updated = await store.get_source_state("manual_source:abc123")
    assert updated["wiki_status"] == "processed"
    assert updated["page_ids"] == ["stock:603738"]

    pending = await store.list_source_states(status="pending")
    assert len(pending) == 0

    processed = await store.list_source_states(status="processed")
    assert len(processed) == 1


@pytest.mark.asyncio
async def test_rebuild_index(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    await store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="正文",
        metadata={"symbol": "603738"},
    )

    result = await store.rebuild_index()
    assert result["page_count"] >= 1
    assert (test_settings.wiki_knowledge_dir / "index.md").exists()

    content = (test_settings.wiki_knowledge_dir / "index.md").read_text(encoding="utf-8")
    assert "603738 泰晶科技" in content


@pytest.mark.asyncio
async def test_base_page_updated_at_stable_when_unchanged(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    home1 = await store.read_page("home:index")
    updated_at_1 = home1["updated_at"]

    # Second init_db with no file changes
    await store.init_db()
    home2 = await store.read_page("home:index")
    updated_at_2 = home2["updated_at"]

    assert updated_at_1 == updated_at_2
    assert home1["content_sha256"] == home2["content_sha256"]


@pytest.mark.asyncio
async def test_base_page_updated_at_changes_when_file_modified(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    home1 = await store.read_page("home:index")
    updated_at_1 = home1["updated_at"]

    # Modify index.md
    index_path = test_settings.wiki_knowledge_dir / "index.md"
    index_path.write_text("# Modified Wiki\n\n", encoding="utf-8")

    await store.init_db()
    home2 = await store.read_page("home:index")
    updated_at_2 = home2["updated_at"]

    assert updated_at_2 != updated_at_1
    assert home2["content_sha256"] != home1["content_sha256"]


@pytest.mark.asyncio
async def test_rebuild_index_creates_placeholder_pages(test_settings):
    store = WikiStore(test_settings)
    await store.init_db()

    result = await store.rebuild_index()
    assert result["page_count"] >= 1

    # Placeholder pages should exist
    for page_id in ("claims:contradictions", "claims:open_questions", "portfolio:overview", "portfolio:trade_review"):
        page = await store.read_page(page_id)
        assert page["page_type"] in {"contradictions", "open_questions", "portfolio_overview", "trade_review"}

    # Index should have links and no broken links to placeholders
    async with __import__("aiosqlite").connect(store.db_path) as db:
        db.row_factory = __import__("aiosqlite").Row
        async with db.execute(
            "SELECT * FROM wiki_page_links WHERE from_page_id = ?", ("home:index",)
        ) as cursor:
            rows = await cursor.fetchall()
            to_page_ids = {r["to_page_id"] for r in rows}
            assert "claims:contradictions" in to_page_ids or "pages/claims/contradictions" in to_page_ids
            assert "claims:open_questions" in to_page_ids or "pages/claims/open_questions" in to_page_ids
            assert "portfolio:overview" in to_page_ids or "pages/portfolio/overview" in to_page_ids
            assert "portfolio:trade_review" in to_page_ids or "pages/portfolio/trade_review" in to_page_ids
