# engine/sentinel/engines/community_scanner.py
"""S1 — Community Signal Scanner.

Scans community sources (Hacker News, Reddit, ProductHunt) for mentions of
tracked competitors. Community complaints become "opportunity" signals;
strong praise becomes "threat" confirmation signals.

Runs weekly on Wednesday at 8 AM (cron: 0 8 * * 3), staggered from the
competitive_observer (Monday 6 AM) to spread load.

Sources:
- HN: Algolia Search API (no key required) — last 30 days
- Reddit: JSON API for r/cursor, r/ClaudeAI, r/LocalLLaMA, r/SoftwareEngineering
- ProductHunt: product search via web (scraped via httpx)
"""

from __future__ import annotations

import logging

import httpx

from core.engine.core.db import parse_rows, pool
from core.engine.sentinel.engines.competitive_observer import (
    classify_signal,
    extract_signals,
)
from core.engine.sentinel.registry import register_engine

logger = logging.getLogger(__name__)

_HN_API = "https://hn.algolia.com/api/v1/search"
_REDDIT_SUBREDDITS = ["cursor", "ClaudeAI", "LocalLLaMA", "SoftwareEngineering"]
_MAX_POSTS_PER_SOURCE = 5  # keep LLM calls bounded

COMMUNITY_EXTRACTION_PROMPT_SUFFIX = """
Focus on:
- Complaints or frustrations users have (→ opportunity for us)
- Features users love or wish existed (→ confirmation if we have it, threat if we don't)
- Migrations away from this tool (→ opportunity)
- Strong praise for a specific capability (→ threat if we lack it)

Ignore: general discussion, support questions, off-topic posts.
"""


async def _fetch_hn_posts(competitor_name: str, days: int = 30) -> list[str]:
    """Return text excerpts from HN posts mentioning the competitor."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _HN_API,
                params={
                    "query": competitor_name,
                    "tags": "story,comment",
                    "numericFilters": f"created_at_i>{__import__('time').time() - days * 86400:.0f}",
                    "hitsPerPage": _MAX_POSTS_PER_SOURCE,
                },
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            return [
                f"HN | {h.get('title') or h.get('comment_text', '')[:200]}"
                for h in hits
                if h.get("title") or h.get("comment_text")
            ]
    except Exception as exc:
        logger.debug("HN fetch failed for %s: %s", competitor_name, exc)
        return []


async def _fetch_reddit_posts(competitor_name: str) -> list[str]:
    """Return text excerpts from Reddit posts mentioning the competitor."""
    results = []
    headers = {"User-Agent": "ACE-CommunityScanner/1.0"}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            for sub in _REDDIT_SUBREDDITS:
                try:
                    resp = await client.get(
                        f"https://www.reddit.com/r/{sub}/search.json",
                        params={"q": competitor_name, "restrict_sr": 1, "limit": 3, "sort": "new"},
                    )
                    resp.raise_for_status()
                    posts = resp.json().get("data", {}).get("children", [])
                    for p in posts:
                        data = p.get("data", {})
                        title = data.get("title", "")
                        selftext = data.get("selftext", "")[:300]
                        if title:
                            results.append(f"r/{sub} | {title}\n{selftext}")
                except Exception:
                    pass
    except Exception as exc:
        logger.debug("Reddit fetch failed for %s: %s", competitor_name, exc)
    return results[:_MAX_POSTS_PER_SOURCE]


async def _scan_competitor_community(comp: dict, db) -> int:
    """Scan community sources for one competitor, write signals, return count."""
    name = comp.get("name", "")
    if not name:
        return 0

    # Gather community posts
    posts = await _fetch_hn_posts(name)
    posts.extend(await _fetch_reddit_posts(name))

    if not posts:
        return 0

    content = "\n\n".join(posts) + "\n\n" + COMMUNITY_EXTRACTION_PROMPT_SUFFIX
    signals = await extract_signals(content, name)

    count = 0
    for sig in signals:
        sig["competitor"] = name
        sig["source_url"] = ""
        sig = await classify_signal(sig)

        await db.query(
            """CREATE competitive_signal SET
                competitor      = $competitor,
                product         = <record>$product,
                title           = $title,
                description     = $description,
                source_url      = $source_url,
                relevance       = $relevance,
                relevance_score = $relevance_score,
                action          = $action,
                urgency         = $urgency,
                rationale       = $rationale,
                signal_source   = 'community',
                created_at      = time::now()
            """,
            {
                "competitor": sig.get("competitor", name),
                "product": comp.get("product", ""),
                "title": sig.get("title", ""),
                "description": sig.get("description", ""),
                "source_url": sig.get("source_url", ""),
                "relevance": sig.get("relevance", "none"),
                "relevance_score": sig.get("relevance_score", 0.5),
                "action": sig.get("action", "monitor"),
                "urgency": sig.get("urgency", "low"),
                "rationale": sig.get("rationale", ""),
            },
        )
        count += 1

    return count


@register_engine(
    name="community_scanner",
    cron="0 8 * * wed",
    description="Scan HN and Reddit for community signals about tracked competitors.",
)
async def run_community_scanner(product_id: str) -> dict:
    """Scan community sources for competitor mentions and extract signals.

    Searches HN Algolia API and Reddit JSON API for Tier 1 competitors.
    Community posts are fed through the standard extraction + classification
    pipeline. Signals with 'relevance: opportunity' indicate competitor pain
    points — our opening.

    Returns: {competitors_scanned, signals_extracted}
    """
    results = {"competitors_scanned": 0, "signals_extracted": 0}

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                # Tier 1 only — community scanning for all tiers is too noisy
                "SELECT id, name, tier, sources, product FROM competitor "
                "WHERE product = <record>$product AND tier = 1 ORDER BY name",
                {"product": product_id},
            )
        )

        for comp in rows:
            # Pass the product_id into the competitor dict for signal writes
            comp["product"] = product_id
            n = await _scan_competitor_community(comp, db)
            results["signals_extracted"] += n
            results["competitors_scanned"] += 1

    logger.info(
        "community_scanner: %s — %d competitors, %d signals",
        product_id,
        results["competitors_scanned"],
        results["signals_extracted"],
    )
    return results
