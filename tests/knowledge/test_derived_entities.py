from src.knowledge.derived_entities import (
    ENTITY_TYPE_STOCK,
    ENTITY_TYPE_DATE,
    ENTITY_TYPE_SOURCE_KIND,
    ENTITY_TYPE_TOPIC,
    ENTITY_TYPE_CLAIM_TYPE,
    extract_entities_from_raw_source,
    extract_entities_from_wiki_page,
    extract_entities_from_claim,
)


def test_extract_stock_from_raw_metadata():
    source = {
        "source_id": "s1",
        "source_kind": "manual_source",
        "metadata": {"symbol": "603738", "symbols": ["000001"]},
        "markdown": "# Test\n\nSome text.",
    }
    entities = extract_entities_from_raw_source(source)
    types = {e["entity_type"] for e in entities}
    assert ENTITY_TYPE_STOCK in types
    keys = {e["canonical_key"] for e in entities if e["entity_type"] == ENTITY_TYPE_STOCK}
    assert "603738" in keys
    assert "000001" in keys


def test_extract_stock_from_raw_body():
    source = {
        "source_id": "s1",
        "source_kind": "news_article",
        "metadata": {},
        "markdown": "股票 603738 和 000001 今日表现良好。",
    }
    entities = extract_entities_from_raw_source(source)
    keys = {e["canonical_key"] for e in entities if e["entity_type"] == ENTITY_TYPE_STOCK}
    assert "603738" in keys
    assert "000001" in keys


def test_extract_date_from_raw():
    source = {
        "source_id": "s1",
        "source_kind": "daily_trade_log",
        "metadata": {"trade_date": "2026-06-05"},
        "markdown": "交易记录 2026-06-04 和 2026-06-05。",
    }
    entities = extract_entities_from_raw_source(source)
    keys = {e["canonical_key"] for e in entities if e["entity_type"] == ENTITY_TYPE_DATE}
    assert "2026-06-05" in keys
    assert "2026-06-04" in keys


def test_extract_source_kind():
    source = {
        "source_id": "s1",
        "source_kind": "announcement",
        "metadata": {},
        "markdown": "正文",
    }
    entities = extract_entities_from_raw_source(source)
    kinds = {e["canonical_key"] for e in entities if e["entity_type"] == ENTITY_TYPE_SOURCE_KIND}
    assert "announcement" in kinds


def test_extract_topic_from_tags():
    source = {
        "source_id": "s1",
        "source_kind": "manual_source",
        "metadata": {"tags": ["topic/ai", "stock/603738"]},
        "markdown": "正文",
    }
    entities = extract_entities_from_raw_source(source)
    topics = {e["canonical_key"] for e in entities if e["entity_type"] == ENTITY_TYPE_TOPIC}
    assert "ai" in topics


def test_extract_wiki_page_entities():
    page = {
        "page_id": "stock:603738",
        "page_type": "stock_profile",
        "title": "603738",
        "frontmatter": {"symbol": "603738", "tags": ["topic/semiconductor"]},
        "markdown": "# 603738\n\n2026-06-05 更新。",
    }
    entities = extract_entities_from_wiki_page(page)
    types = {e["entity_type"] for e in entities}
    assert ENTITY_TYPE_STOCK in types
    assert ENTITY_TYPE_DATE in types
    assert ENTITY_TYPE_TOPIC in types


def test_extract_wiki_topic_page():
    page = {
        "page_id": "topic:ai",
        "page_type": "topic",
        "title": "AI 算力",
        "frontmatter": {"topic": "ai"},
        "markdown": "# AI\n\n定义。",
    }
    entities = extract_entities_from_wiki_page(page)
    topics = {e["canonical_key"] for e in entities if e["entity_type"] == ENTITY_TYPE_TOPIC}
    assert "ai" in topics


def test_extract_claim_type():
    claim = {
        "claim_id": "c1",
        "claim_type": "fact",
        "statement": "测试",
        "source_ids": ["s1"],
    }
    entities = extract_entities_from_claim(claim)
    assert len(entities) == 1
    assert entities[0]["entity_type"] == ENTITY_TYPE_CLAIM_TYPE
    assert entities[0]["canonical_key"] == "fact"
