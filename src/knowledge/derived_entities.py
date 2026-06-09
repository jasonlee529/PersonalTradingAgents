from __future__ import annotations

import re
from datetime import datetime


ENTITY_TYPE_STOCK = "stock"
ENTITY_TYPE_TOPIC = "topic"
ENTITY_TYPE_SOURCE_KIND = "source_kind"
ENTITY_TYPE_CLAIM_TYPE = "claim_type"
ENTITY_TYPE_DATE = "date"
ENTITY_TYPE_UNKNOWN = "unknown"

_STOCK_PATTERN = re.compile(r"\b\d{6}\b")
_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def _stable_id(entity_type: str, key: str) -> str:
    import hashlib
    h = hashlib.sha256(f"{entity_type}:{key}".encode("utf-8")).hexdigest()[:12]
    return f"{entity_type}:{key}:{h}"


def extract_entities_from_raw_source(source: dict) -> list[dict]:
    """Extract entities from a raw source record."""
    entities = []
    metadata = source.get("metadata") or {}

    # Stock symbols
    symbols = set()
    for key in ("symbol", "symbols"):
        val = metadata.get(key)
        if isinstance(val, str) and val.strip():
            symbols.add(val.strip())
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v.strip():
                    symbols.add(v.strip())

    # Also scan body for 6-digit numbers
    body = source.get("markdown", "")
    for m in _STOCK_PATTERN.finditer(body):
        symbols.add(m.group())

    for sym in sorted(symbols):
        entities.append({
            "entity_id": _stable_id("stock", sym),
            "entity_type": ENTITY_TYPE_STOCK,
            "name": sym,
            "canonical_key": sym,
            "metadata": {"extracted_from": "raw_source", "source_id": source.get("source_id", "")},
        })

    # Source kind
    source_kind = source.get("source_kind", "")
    if source_kind:
        entities.append({
            "entity_id": _stable_id("source_kind", source_kind),
            "entity_type": ENTITY_TYPE_SOURCE_KIND,
            "name": source_kind,
            "canonical_key": source_kind,
            "metadata": {"extracted_from": "raw_source"},
        })

    # Dates
    dates = set()
    trade_date = metadata.get("trade_date")
    if trade_date:
        dates.add(str(trade_date))
    published_at = metadata.get("published_at")
    if published_at and len(str(published_at)) >= 10:
        dates.add(str(published_at)[:10])
    for m in _DATE_PATTERN.finditer(body):
        dates.add(m.group(1))

    for d in sorted(dates):
        entities.append({
            "entity_id": _stable_id("date", d),
            "entity_type": ENTITY_TYPE_DATE,
            "name": d,
            "canonical_key": d,
            "metadata": {"extracted_from": "raw_source"},
        })

    # Topics from tags (tags are at root level in normalized raw records)
    tags = source.get("tags") or metadata.get("tags") or []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("topic/"):
            topic_name = tag[6:]
            entities.append({
                "entity_id": _stable_id("topic", topic_name),
                "entity_type": ENTITY_TYPE_TOPIC,
                "name": topic_name,
                "canonical_key": topic_name,
                "metadata": {"extracted_from": "raw_source", "tag": tag},
            })

    return entities


def extract_entities_from_wiki_page(page: dict) -> list[dict]:
    """Extract entities from a wiki page record."""
    entities = []
    metadata = page.get("frontmatter") or page.get("metadata") or {}
    body = page.get("markdown", "")
    page_id = page.get("page_id", "")
    page_type = page.get("page_type", "")

    # Stock symbols
    symbols = set()
    symbol = metadata.get("symbol")
    if isinstance(symbol, str) and symbol.strip():
        symbols.add(symbol.strip())
    for m in _STOCK_PATTERN.finditer(body):
        symbols.add(m.group())

    for sym in sorted(symbols):
        entities.append({
            "entity_id": _stable_id("stock", sym),
            "entity_type": ENTITY_TYPE_STOCK,
            "name": sym,
            "canonical_key": sym,
            "metadata": {"extracted_from": "wiki_page", "page_id": page_id},
        })

    # Topics from page_type=topic
    if page_type == "topic":
        topic = metadata.get("topic") or metadata.get("title") or ""
        if topic:
            entities.append({
                "entity_id": _stable_id("topic", topic),
                "entity_type": ENTITY_TYPE_TOPIC,
                "name": topic,
                "canonical_key": topic,
                "metadata": {"extracted_from": "wiki_page", "page_id": page_id},
            })

    # Dates
    dates = set()
    trade_date = metadata.get("trade_date")
    if trade_date:
        dates.add(str(trade_date))
    for m in _DATE_PATTERN.finditer(body):
        dates.add(m.group(1))

    for d in sorted(dates):
        entities.append({
            "entity_id": _stable_id("date", d),
            "entity_type": ENTITY_TYPE_DATE,
            "name": d,
            "canonical_key": d,
            "metadata": {"extracted_from": "wiki_page", "page_id": page_id},
        })

    # Tags as topics
    tags = metadata.get("tags") or []
    for tag in tags:
        if isinstance(tag, str) and tag.startswith("topic/"):
            topic_name = tag[6:]
            entities.append({
                "entity_id": _stable_id("topic", topic_name),
                "entity_type": ENTITY_TYPE_TOPIC,
                "name": topic_name,
                "canonical_key": topic_name,
                "metadata": {"extracted_from": "wiki_page", "page_id": page_id, "tag": tag},
            })

    return entities


def extract_entities_from_claim(claim: dict) -> list[dict]:
    """Extract claim_type entity from a wiki claim."""
    entities = []
    claim_type = claim.get("claim_type", "")
    if claim_type:
        entities.append({
            "entity_id": _stable_id("claim_type", claim_type),
            "entity_type": ENTITY_TYPE_CLAIM_TYPE,
            "name": claim_type,
            "canonical_key": claim_type,
            "metadata": {"extracted_from": "claim", "claim_id": claim.get("claim_id", "")},
        })
    return entities
