"""Related idea and insight detection — find near-matches on capture."""

from __future__ import annotations

import functools
import logging
import re

from core.engine.core.db import parse_rows, pool

logger = logging.getLogger(__name__)

# Common English stopwords to filter out
_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could and or but not no nor so yet for at by to "
    "from in on of with as it its this that these those i we you he she they me "
    "us him her them my our your his their over".split()
)


@functools.lru_cache(maxsize=512)
def _tokenize(text: str) -> frozenset[str]:
    """Tokenize text into lowercase words, filtering stopwords.

    Result is cached (LRU, 512 entries) — the same idea text is compared against
    many candidates in find_similar_ideas, so tokenization cost is paid once.
    Returns frozenset for hashability (required by lru_cache).
    """
    words = frozenset(re.findall(r"[a-z0-9]+", text.lower())) - _STOPWORDS
    return words


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute Jaccard similarity between two texts."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


async def find_similar_ideas(text: str, product_id: str, threshold: float = 0.3, limit: int = 5) -> list[dict]:
    """Find ideas with keyword overlap above threshold.

    Searches ideas in non-terminal states (captured, qualifying, incubating, ready, active).
    Returns list of {id, title, status, similarity} sorted by similarity descending.
    """
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """
                SELECT id, title, raw_input, status, created_at FROM idea
                WHERE product = <record>$product AND status IN ['captured', 'qualifying', 'incubating', 'ready', 'active']
                ORDER BY created_at DESC
                LIMIT 50
                """,
                {"product": product_id},
            )
        )

    matches = []
    for idea in rows:
        compare_text = f"{idea.get('title', '')} {idea.get('raw_input', '')}"
        sim = jaccard_similarity(text, compare_text)
        if sim >= threshold:
            matches.append(
                {
                    "id": str(idea.get("id", "")),
                    "title": idea.get("title", ""),
                    "status": idea.get("status", ""),
                    "similarity": round(sim, 2),
                }
            )

    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches[:limit]


async def find_related_insights(text: str, domain_path: str, product_id: str, limit: int = 5) -> list[dict]:
    """Find insights related to the idea text in the same domain.

    Returns list of {id, content, confidence, domain_path} sorted by confidence descending.
    """
    tokens = _tokenize(text)
    if not tokens:
        return []

    async with pool.connection() as db:
        # Search insights with content matching any keyword
        rows = parse_rows(
            await db.query(
                """
                SELECT id, content, confidence, domain_path FROM insight
                WHERE product = <record>$product AND status = 'active'
                ORDER BY confidence DESC
                LIMIT 100
                """,
                {"product": product_id},
            )
        )

    matches = []
    for insight in rows:
        content = insight.get("content", "")
        sim = jaccard_similarity(text, content)
        if sim >= 0.15:  # Lower threshold for insights (they're shorter)
            matches.append(
                {
                    "id": str(insight.get("id", "")),
                    "content": content[:200],
                    "confidence": insight.get("confidence", 0),
                    "domain_path": insight.get("domain_path", ""),
                    "similarity": round(sim, 2),
                }
            )

    matches.sort(key=lambda x: x["confidence"], reverse=True)
    return matches[:limit]
