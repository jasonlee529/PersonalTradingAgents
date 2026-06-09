"""Markdown formatting and chunking utilities for notifications."""

import re
from typing import List

import markdown2

TRUNCATION_SUFFIX = "\n\n...(本段内容过长已截断)"
PAGE_MARKER_PREFIX = "\n\n📄"
PAGE_MARKER_SAFE_BYTES = 16
MIN_MAX_BYTES = 40


_SPECIAL_CHAR_REGEX = re.compile(r'[\U00010000-\U000FFFFF]')


def _page_marker(i: int, total: int) -> str:
    return f"{PAGE_MARKER_PREFIX} {i+1}/{total}"


def _count_special_chars(s: str) -> int:
    return len(_SPECIAL_CHAR_REGEX.findall(s))


def _effective_len(s: str, special_char_len: int = 2) -> int:
    return len(s) + _count_special_chars(s) * (special_char_len - 1)


def _bytes(s: str) -> int:
    return len(s.encode("utf-8"))


def slice_at_max_bytes(text: str, max_bytes: int) -> tuple[str, str]:
    """Truncate text at a byte boundary without splitting a UTF-8 character."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, ""
    truncated = encoded[:max_bytes]
    # If truncated decodes cleanly, the cut is at a character boundary
    try:
        result = truncated.decode("utf-8")
        return result, text[len(result):]
    except UnicodeDecodeError:
        pass
    # Backtrack up to 3 bytes to find the last valid character boundary
    for i in range(1, min(4, len(truncated))):
        try:
            result = truncated[:-i].decode("utf-8")
            return result, text[len(result):]
        except UnicodeDecodeError:
            continue
    return "", text


def _chunk_by_separators(content: str) -> tuple[list[str], str]:
    """Split content by natural separators for intelligent chunking."""
    if "\n---\n" in content:
        return content.split("\n---\n"), "\n---\n"
    elif "\n# " in content:
        parts = content.split("\n## ")
        return [parts[0]] + [f"## {p}" for p in parts[1:]], "\n"
    elif "\n## " in content:
        parts = content.split("\n## ")
        return [parts[0]] + [f"## {p}" for p in parts[1:]], "\n"
    elif "\n### " in content:
        parts = content.split("\n### ")
        return [parts[0]] + [f"### {p}" for p in parts[1:]], "\n"
    elif "\n**" in content:
        parts = content.split("\n**")
        return [parts[0]] + [f"**{p}" for p in parts[1:]], "\n"
    elif "\n" in content:
        return content.split("\n"), "\n"
    return [content], ""


def _chunk_by_max_bytes(content: str, max_bytes: int) -> List[str]:
    if _bytes(content) <= max_bytes:
        return [content]
    if max_bytes < MIN_MAX_BYTES:
        raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}")

    sections = []
    suffix = TRUNCATION_SUFFIX
    effective_max = max_bytes - _bytes(suffix)
    if effective_max <= 0:
        effective_max = max_bytes
        suffix = ""

    while True:
        chunk, content = slice_at_max_bytes(content, effective_max)
        if content.strip() != "":
            sections.append(chunk + suffix)
        else:
            sections.append(chunk)
            break
    return sections


def chunk_content_by_max_bytes(content: str, max_bytes: int, add_page_marker: bool = False) -> List[str]:
    """Intelligently split content by byte length, respecting section boundaries."""
    def _chunk(content: str, max_bytes: int) -> List[str]:
        if max_bytes < MIN_MAX_BYTES:
            raise ValueError(f"max_bytes={max_bytes} < {MIN_MAX_BYTES}")
        if _bytes(content) <= max_bytes:
            return [content]

        sections, separator = _chunk_by_separators(content)
        if separator == "" and len(sections) == 1:
            return _chunk_by_max_bytes(content, max_bytes)

        chunks: List[str] = []
        current_chunk: List[str] = []
        current_bytes = 0
        separator_bytes = _bytes(separator) if separator else 0
        effective_max = max_bytes - separator_bytes

        for section in sections:
            section += separator
            section_bytes = _bytes(section)

            if section_bytes > effective_max:
                if current_chunk:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_bytes = 0
                section_chunks = _chunk(section[:-separator_bytes], effective_max)
                section_chunks[-1] = section_chunks[-1] + separator
                chunks.extend(section_chunks)
                continue

            if current_bytes + section_bytes > effective_max:
                if current_chunk:
                    chunks.append("".join(current_chunk))
                current_chunk = [section]
                current_bytes = section_bytes
            else:
                current_chunk.append(section)
                current_bytes += section_bytes

        if current_chunk:
            chunks.append("".join(current_chunk))

        if (chunks and len(chunks[-1]) > separator_bytes and
            chunks[-1][-separator_bytes:] == separator):
            chunks[-1] = chunks[-1][:-separator_bytes]

        return chunks

    if add_page_marker:
        max_bytes = max_bytes - PAGE_MARKER_SAFE_BYTES

    chunks = _chunk(content, max_bytes)
    if add_page_marker:
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            chunks[i] = chunk + _page_marker(i, total)
    return chunks


def format_feishu_markdown(content: str) -> str:
    """Convert standard Markdown to Feishu lark_md friendly format."""
    def _flush_table_rows(buffer: List[str], output: List[str]) -> None:
        if not buffer:
            return

        def _parse_row(row: str) -> List[str]:
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            return [c for c in cells if c]

        rows = []
        for raw in buffer:
            if re.match(r'^\s*\|?\s*[:-]+\s*(\|\s*[:-]+\s*)+\|?\s*$', raw):
                continue
            parsed = _parse_row(raw)
            if parsed:
                rows.append(parsed)

        if not rows:
            return

        header = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        for row in data_rows:
            pairs = []
            for idx, cell in enumerate(row):
                key = header[idx] if idx < len(header) else f"列{idx + 1}"
                pairs.append(f"{key}：{cell}")
            output.append(f"• {' | '.join(pairs)}")

    lines = []
    table_buffer: List[str] = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("|"):
            table_buffer.append(line)
            continue

        if table_buffer:
            _flush_table_rows(table_buffer, lines)
            table_buffer = []

        if re.match(r'^#{1,6}\s+', line):
            title = re.sub(r'^#{1,6}\s+', '', line).strip()
            line = f"**{title}**" if title else ""
        elif line.startswith("> "):
            quote = line[2:].strip()
            line = f"💬 {quote}" if quote else ""
        elif line.strip() == "---":
            line = "────────"
        elif line.startswith("- "):
            line = f"• {line[2:].strip()}"

        lines.append(line)

    if table_buffer:
        _flush_table_rows(table_buffer, lines)

    return "\n".join(lines).strip()


def markdown_to_html_document(markdown_text: str) -> str:
    """Convert Markdown to a complete HTML document for email."""
    html_content = markdown2.markdown(
        markdown_text,
        extras=["tables", "fenced-code-blocks", "break-on-newline", "cuddled-lists"],
    )

    css_style = """
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
                line-height: 1.5;
                color: #24292e;
                font-size: 14px;
                padding: 15px;
                max-width: 900px;
                margin: 0 auto;
            }
            h1 { font-size: 20px; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; margin-top: 1.2em; margin-bottom: 0.8em; color: #0366d6; }
            h2 { font-size: 18px; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; margin-top: 1.0em; margin-bottom: 0.6em; }
            h3 { font-size: 16px; margin-top: 0.8em; margin-bottom: 0.4em; }
            p { margin-top: 0; margin-bottom: 8px; }
            table { border-collapse: collapse; width: 100%; margin: 12px 0; display: block; overflow-x: auto; font-size: 13px; }
            th, td { border: 1px solid #dfe2e5; padding: 6px 10px; text-align: left; }
            th { background-color: #f6f8fa; font-weight: 600; }
            tr:nth-child(2n) { background-color: #f8f8f8; }
            blockquote { color: #6a737d; border-left: 0.25em solid #dfe2e5; padding: 0 1em; margin: 0 0 10px 0; }
            code { padding: 0.2em 0.4em; margin: 0; font-size: 85%; background-color: rgba(27,31,35,0.05); border-radius: 3px; }
            pre { padding: 12px; overflow: auto; line-height: 1.45; background-color: #f6f8fa; border-radius: 3px; margin-bottom: 10px; }
            hr { height: 0.25em; padding: 0; margin: 16px 0; background-color: #e1e4e8; border: 0; }
            ul, ol { padding-left: 20px; margin-bottom: 10px; }
            li { margin: 2px 0; }
        """

    return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><style>{css_style}</style></head>
        <body>{html_content}</body>
        </html>
        """
