import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.knowledge.raw_store import RawStore
from src.knowledge.wiki_store import WikiStore


@pytest.fixture
def wiki_client(test_settings):
    app = create_app(test_settings)
    return TestClient(app)


def test_wiki_pages_list(wiki_client):
    resp = wiki_client.get("/api/wiki/pages")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_wiki_pending_sources(wiki_client, test_settings):
    # Create a raw source first
    raw_store = RawStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    asyncio.run(raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Pending Source",
        markdown="# Test\n\nBody",
        metadata={"symbols": ["603738"]},
    ))

    resp = wiki_client.get("/api/wiki/sources/pending")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_wiki_preview_mode_rejected(wiki_client, test_settings):
    raw_store = RawStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    source = asyncio.run(raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Preview Rejected Source",
        markdown="# Test\n\nBody",
        metadata={"symbols": ["603738"]},
    ))

    resp = wiki_client.post(f"/api/wiki/ingest/source/{source['source_id']}", json={"mode": "preview"})
    assert resp.status_code == 422


def test_wiki_apply_ingest(wiki_client, test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    asyncio.run(wiki_store.init_db())
    source = asyncio.run(raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Apply Source",
        markdown="# Test\n\nBody",
        metadata={"symbols": ["603738"]},
    ))

    resp = wiki_client.post(f"/api/wiki/ingest/source/{source['source_id']}", json={"force": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["run_id"]

    state = asyncio.run(wiki_store.get_source_state(source["source_id"]))
    assert state["wiki_status"] == "queued"
    assert state["latest_ingest_run_id"] == data["run_id"]

    pending = wiki_client.get("/api/wiki/sources/pending").json()
    row = next(item for item in pending if item["source_id"] == source["source_id"])
    assert row["wiki_status"] == "queued"


def test_wiki_page_detail(wiki_client, test_settings):
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(wiki_store.init_db())
    asyncio.run(wiki_store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738 泰晶科技",
        slug="stocks/603738",
        markdown="# 603738\n\n测试",
        metadata={"symbol": "603738"},
    ))

    resp = wiki_client.get("/api/wiki/pages/stock:603738")
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_id"] == "stock:603738"

    resp2 = wiki_client.get("/api/wiki/pages/stock:603738/content")
    assert resp2.status_code == 200
    assert "603738" in resp2.json()["content"]


def test_wiki_verify_page(wiki_client, test_settings):
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(wiki_store.init_db())
    asyncio.run(wiki_store.upsert_page(
        page_id="stock:603738",
        page_type="stock_profile",
        title="603738",
        slug="stocks/603738",
        markdown="正文",
        metadata={"symbol": "603738"},
    ))

    resp = wiki_client.post("/api/wiki/pages/stock:603738/verify")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_wiki_analysis_run_ingest(wiki_client, test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    asyncio.run(wiki_store.init_db())
    run_id = "analysis:603738:2026-06-05:095641"
    s1 = asyncio.run(raw_store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 市场分析",
        markdown="# 市场\n\n...",
        metadata={"symbol": "603738", "trade_date": "2026-06-05", "run_id": run_id, "analysis_node": "market_report"},
    ))
    s2 = asyncio.run(raw_store.add_source(
        source_kind="stock_analysis",
        origin="agent",
        title="603738 情绪分析",
        markdown="# 情绪\n\n...",
        metadata={"symbol": "603738", "trade_date": "2026-06-05", "run_id": run_id, "analysis_node": "sentiment_report"},
    ))

    resp = wiki_client.post(f"/api/wiki/ingest/analysis-run/{run_id}", json={"force": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert set(data["source_ids"]) == {s1["source_id"], s2["source_id"]}

    for sid in [s1["source_id"], s2["source_id"]]:
        state = asyncio.run(wiki_store.get_source_state(sid))
        assert state["wiki_status"] == "queued"
        assert state["latest_ingest_run_id"] == data["run_id"]


def test_wiki_batch_ingest_applies_only(wiki_client, test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    asyncio.run(wiki_store.init_db())
    source = asyncio.run(raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Batch Apply Source",
        markdown="# Batch\n\nBody",
        metadata={"symbols": ["603738"]},
    ))

    resp = wiki_client.post("/api/wiki/ingest/batch", json={"source_ids": [source["source_id"]]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["batch_status"] == "queued"
    results = data["results"]
    assert len(results) == 1
    assert results[0]["status"] == "queued"


def test_wiki_ingest_same_source_reuses_running_run(wiki_client, test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    asyncio.run(wiki_store.init_db())
    source = asyncio.run(raw_store.add_source(
        source_kind="manual_source",
        origin="user",
        title="Repeat Apply Source",
        markdown="# Repeat\n\nBody",
        metadata={"symbols": ["603738"]},
    ))

    first = wiki_client.post(f"/api/wiki/ingest/source/{source['source_id']}", json={}).json()
    second_resp = wiki_client.post(f"/api/wiki/ingest/source/{source['source_id']}", json={})
    assert second_resp.status_code == 200
    second = second_resp.json()
    assert second["status"] == "queued"
    assert second["run_id"] == first["run_id"]
    assert "already queued" in second["warnings"][0].lower()


def test_wiki_ingest_rejects_when_more_than_ten_running(wiki_client, test_settings):
    raw_store = RawStore(test_settings)
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(raw_store.init_db())
    asyncio.run(wiki_store.init_db())

    sources = [
        asyncio.run(raw_store.add_source(
            source_kind="daily_trade_log",
            origin="user",
            title=f"Queued Source {i}",
            markdown=f"# Source {i}\n\nBody",
            metadata={"trade_date": f"2026-06-{i + 1:02d}"},
        ))
        for i in range(11)
    ]

    for source in sources[:10]:
        resp = wiki_client.post(f"/api/wiki/ingest/source/{source['source_id']}", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    rejected = wiki_client.post(f"/api/wiki/ingest/source/{sources[10]['source_id']}", json={})
    assert rejected.status_code == 409
    assert "10" in rejected.json()["detail"]


def test_wiki_pages_search_by_title(wiki_client, test_settings):
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(wiki_store.init_db())
    asyncio.run(wiki_store.upsert_page(
        page_id="stock:SEARCH01",
        page_type="stock_profile",
        title="Searchable Test Stock",
        slug="stocks/SEARCH01",
        markdown="# SEARCH01\n\nTest body content",
        metadata={"symbol": "SEARCH01"},
    ))

    resp = wiki_client.get("/api/wiki/pages?q=Searchable")
    assert resp.status_code == 200
    data = resp.json()
    assert any(p["page_id"] == "stock:SEARCH01" for p in data)


def test_wiki_pages_search_by_body(wiki_client, test_settings):
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(wiki_store.init_db())
    asyncio.run(wiki_store.upsert_page(
        page_id="stock:SEARCH02",
        page_type="stock_profile",
        title="Another Stock",
        slug="stocks/SEARCH02",
        markdown="# SEARCH02\n\nUniqueBodyContentForSearch",
        metadata={"symbol": "SEARCH02"},
    ))

    resp = wiki_client.get("/api/wiki/pages?q=UniqueBodyContentForSearch")
    assert resp.status_code == 200
    data = resp.json()
    assert any(p["page_id"] == "stock:SEARCH02" for p in data)


def test_wiki_save_query(wiki_client, test_settings):
    wiki_store = WikiStore(test_settings)
    import asyncio
    asyncio.run(wiki_store.init_db())

    resp = wiki_client.post("/api/wiki/query/save", json={
        "question": "603738 应该买入还是观望？",
        "answer_markdown": "建议观望，当前估值偏高。",
        "cited_page_ids": ["stock:603738"],
        "cited_source_ids": ["manual_source:test_001"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["page_type"] == "saved_query"
    assert "query:" in data["page_id"]

    # Verify page exists
    page = asyncio.run(wiki_store.read_page(data["page_id"]))
    assert "603738 应该买入还是观望？" in page["markdown"]
    assert "建议观望" in page["markdown"]


def test_wiki_claims_returns_normalised_lists(wiki_client, test_settings):
    wiki_store = WikiStore(test_settings)
    import asyncio
    import aiosqlite
    asyncio.run(wiki_store.init_db())

    async def insert_claim():
        async with aiosqlite.connect(wiki_store.db_path) as db:
            await db.execute(
                """INSERT INTO wiki_claims
                   (claim_id, subject_type, subject_id, claim_type, statement, polarity,
                    status, confidence, source_ids_json, page_ids_json, contradicts_json,
                    metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "claim:normalised",
                    "stock",
                    "603738",
                    "fact",
                    "规范化测试",
                    "",
                    "active",
                    0.6,
                    '["manual_source:test"]',
                    '["source_digest:test"]',
                    "[]",
                    "{}",
                    "2026-06-05",
                    "2026-06-05",
                ),
            )
            await db.commit()

    asyncio.run(insert_claim())

    resp = wiki_client.get("/api/wiki/claims")
    assert resp.status_code == 200
    row = next(item for item in resp.json() if item["claim_id"] == "claim:normalised")
    assert row["confidence"] == 0.6
    assert row["source_ids"] == ["manual_source:test"]
    assert row["page_ids"] == ["source_digest:test"]
