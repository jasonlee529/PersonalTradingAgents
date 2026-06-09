from src.knowledge.derived_chunker import chunk_markdown


def test_chunk_markdown_strips_frontmatter():
    md = "---\ntitle: Test\n---\n\n# Heading\n\nBody text."
    chunks = chunk_markdown(md, doc_id="doc:1", doc_type="wiki_page")
    assert len(chunks) >= 1
    for c in chunks:
        assert "title: Test" not in c["text"]
        assert "---" not in c["text"]


def test_chunk_markdown_by_headings():
    md = (
        "# Summary\n\nSummary content here.\n\n"
        "# Risks\n\nRisk content here.\n\n"
        "# Catalysts\n\nCatalyst content here.\n"
    )
    chunks = chunk_markdown(md, doc_id="doc:1", doc_type="wiki_page")
    # Small sections may merge; at minimum we get heading info preserved
    assert len(chunks) >= 1
    headings = [c["heading_path"] for c in chunks]
    assert any("Summary" in h or "Risks" in h or "Catalysts" in h for h in headings)


def test_chunk_markdown_short_doc_single_chunk():
    md = "# Short\n\nJust a little text."
    chunks = chunk_markdown(md, doc_id="doc:1", doc_type="wiki_page")
    assert len(chunks) == 1
    assert chunks[0]["ordinal"] == 0


def test_chunk_markdown_merge_small_sections():
    md = (
        "# A\n\nShort.\n\n"
        "# B\n\nAlso short.\n\n"
        "# C\n\n" + "x.\n" * 500
    )
    chunks = chunk_markdown(md, doc_id="doc:1", doc_type="wiki_page")
    # A and B should merge because they're small; C stays separate
    assert len(chunks) <= 2


def test_chunk_markdown_empty_body():
    md = "---\ntitle: T\n---\n\n"
    chunks = chunk_markdown(md, doc_id="doc:1", doc_type="wiki_page")
    assert chunks == []


def test_chunk_id_format():
    md = "# H\n\nText."
    chunks = chunk_markdown(md, doc_id="doc:1", doc_type="wiki_page")
    assert chunks[0]["chunk_id"] == "doc:1:c0"
    assert chunks[0]["doc_id"] == "doc:1"
    assert chunks[0]["doc_type"] == "wiki_page"
