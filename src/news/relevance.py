import re
from typing import Optional


def compute_relevance(
    title: str,
    content: str,
    symbol: str,
    name: str = "",
    keywords: list[str] = None,
) -> float:
    """Score relevance of a news item to a given stock.

    Returns 0.0-1.0. Exact symbol/name match = high score.
    """
    text = f"{title} {content}".lower()
    score = 0.0

    # Symbol match (exact)
    if symbol.lower() in text:
        score += 0.5

    # Name match
    if name and name.lower() in text:
        score += 0.4

    # Keyword matches
    keywords = keywords or []
    keyword_hits = sum(1 for kw in keywords if kw.lower() in text)
    score += min(keyword_hits * 0.1, 0.2)

    return min(score, 1.0)
