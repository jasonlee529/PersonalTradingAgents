import pytest
from src.news.collector import NewsConceptExtractor


@pytest.fixture
def extractor():
    return NewsConceptExtractor()


def test_extract_concepts_from_title(extractor):
    news_items = [
        {"title": "固态电池技术突破，宁德时代发布新品"},
        {"title": "低空经济政策出台，飞行器制造受益"},
        {"title": "白酒板块震荡，贵州茅台企稳"},
    ]
    concepts = extractor.extract(news_items)
    assert "固态电池" in concepts
    assert "低空经济" in concepts
    assert "白酒" not in concepts  # Not in CONCEPT_KEYWORDS (it's in INDUSTRY_KEYWORDS)


def test_extract_concepts_deduplicates(extractor):
    news_items = [
        {"title": "固态电池量产在即"},
        {"title": "固态电池产业链调研"},
    ]
    concepts = extractor.extract(news_items)
    # Should dedupe — "固态电池" appears once
    assert concepts.count("固态电池") == 1


def test_extract_concepts_empty(extractor):
    assert extractor.extract([]) == []
    assert extractor.extract([{"title": "无关新闻"}]) == []


def test_extract_concepts_alias_mapping(extractor):
    # "AI算力" and "算力" are both in CONCEPT_KEYWORDS as separate concepts
    news_items = [
        {"title": "AI算力需求爆发"},
        {"title": "算力基建加速"},
    ]
    concepts = extractor.extract(news_items)
    assert "AI算力" in concepts
    assert "算力" in concepts
