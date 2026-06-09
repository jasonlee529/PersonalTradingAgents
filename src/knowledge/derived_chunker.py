from __future__ import annotations

import hashlib
import re


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_frontmatter(markdown: str) -> tuple[str, str]:
    if markdown.startswith("---\n"):
        end = markdown.find("\n---", 4)
        if end != -1:
            frontmatter = markdown[4:end]
            body = markdown[end + 4:].lstrip("\n")
            return frontmatter, body
    return "", markdown


def _token_estimate(text: str) -> int:
    """Rough token estimate: 1 token ~ 1.5 chars for Chinese, ~4 for English."""
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - cn_chars
    return int(cn_chars / 1.5 + other_chars / 4)


def _split_by_headings(body: str) -> list[tuple[str, str]]:
    """Split body into (heading_path, section_text) pairs."""
    lines = body.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading_path: list[str] = []
    current_lines: list[str] = []

    def flush():
        if current_lines:
            heading_path = " > ".join(current_heading_path) if current_heading_path else ""
            sections.append((heading_path, "\n".join(current_lines).strip()))
            current_lines.clear()

    heading_pattern = re.compile(r"^(#{1,6})\s+(.*)$")

    for line in lines:
        m = heading_pattern.match(line)
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            # Adjust heading path to current level
            current_heading_path = current_heading_path[: level - 1]
            current_heading_path.append(title)
            current_lines.append(line)
        else:
            current_lines.append(line)

    flush()
    return sections


def _merge_small_sections(sections: list[tuple[str, str]], min_chars: int = 800, max_chars: int = 1500) -> list[tuple[str, str]]:
    """Merge consecutive small sections while staying under max_chars."""
    if not sections:
        return []

    merged: list[tuple[str, str]] = []
    current_path = sections[0][0]
    current_text = sections[0][1]

    for heading_path, text in sections[1:]:
        combined_len = len(current_text) + len(text)
        if combined_len <= max_chars and len(current_text) < min_chars:
            current_text = (current_text + "\n\n" + text).strip()
            if heading_path:
                current_path = heading_path
        else:
            merged.append((current_path, current_text))
            current_path = heading_path
            current_text = text

    merged.append((current_path, current_text))
    return merged


def chunk_markdown(
    markdown: str,
    *,
    doc_id: str,
    doc_type: str,
    metadata: dict | None = None,
) -> list[dict]:
    """Split markdown into chunks. Returns list of chunk dicts."""
    _frontmatter, body = _extract_frontmatter(markdown)
    body = body.strip()
    if not body:
        return []

    sections = _split_by_headings(body)
    if not sections:
        sections = [("", body)]

    chunks = _merge_small_sections(sections)

    result = []
    for ordinal, (heading_path, text) in enumerate(chunks):
        chunk_id = f"{doc_id}:c{ordinal}"
        result.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "doc_type": doc_type,
            "ordinal": ordinal,
            "heading_path": heading_path,
            "text": text,
            "text_sha256": _sha256_text(text),
            "token_estimate": _token_estimate(text),
            "metadata": dict(metadata or {}),
        })
    return result
