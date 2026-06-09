import pytest

from src.knowledge.wiki_schema import WikiSchema, DEFAULT_WIKI_SCHEMA


@pytest.mark.asyncio
async def test_ensure_schema_creates_file(test_settings):
    schema = WikiSchema(test_settings)
    path = await schema.ensure_schema()
    assert path.exists()
    assert "wiki-maintainer.md" in str(path)


@pytest.mark.asyncio
async def test_read_schema_returns_content(test_settings):
    schema = WikiSchema(test_settings)
    await schema.ensure_schema()
    content = await schema.read_schema()
    assert "分层" in content
    assert "页面类型" in content
    assert "claim" in content
    assert "禁止事项" in content


@pytest.mark.asyncio
async def test_default_schema_has_required_sections():
    assert "raw" in DEFAULT_WIKI_SCHEMA
    assert "wiki" in DEFAULT_WIKI_SCHEMA
    assert "derived" in DEFAULT_WIKI_SCHEMA
    assert "source_digest" in DEFAULT_WIKI_SCHEMA
    assert "analysis_run_digest" in DEFAULT_WIKI_SCHEMA
    assert "stock_profile" in DEFAULT_WIKI_SCHEMA
    assert "claim" in DEFAULT_WIKI_SCHEMA
    assert "禁止事项" in DEFAULT_WIKI_SCHEMA
