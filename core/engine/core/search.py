"""Web search abstraction — wraps external search APIs.

Used by the domain research agent for scoped external research.
Falls back gracefully when no API key is configured.
"""

from __future__ import annotations

import logging

import httpx

from core.engine.core.config import settings

logger = logging.getLogger(__name__)


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Execute a web search and return results.

    Returns list of {title, url, snippet, relevance_score}.
    Returns empty list if no search API is configured.
    """
    api_key = getattr(settings, "search_api_key", None)
    if not api_key:
        logger.debug("No SEARCH_API_KEY configured — skipping web search")
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("results", [])[:max_results]:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", "")[:500],
                    "relevance_score": item.get("score", 0.5),
                }
            )
        return results

    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return []


async def github_search(
    query: str,
    max_results: int = 10,
    sort: str = "stars",
    min_stars: int = 50,
    language: str | None = None,
    created_after: str | None = None,
) -> list[dict]:
    """Search GitHub repos. Returns list of {name, url, description, stars, updated_at, topics, language}.

    Returns empty list if no github_token configured or on any error.
    """
    token = getattr(settings, "github_token", None)
    if not token:
        logger.debug("No github_token configured — skipping GitHub search")
        return []

    qualifiers = f"{query} stars:>={min_stars}"
    if language:
        qualifiers += f" language:{language}"
    if created_after:
        qualifiers += f" created:>={created_after}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": qualifiers, "sort": sort, "per_page": max_results},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()

            remaining = resp.headers.get("X-RateLimit-Remaining", "1")
            if remaining == "0":
                logger.warning("GitHub API rate limit exhausted")
                return []

            data = resp.json()

        return [
            {
                "name": item.get("full_name", ""),
                "url": item.get("html_url", ""),
                "description": item.get("description", "") or "",
                "stars": item.get("stargazers_count", 0),
                "updated_at": item.get("pushed_at", ""),
                "topics": item.get("topics", []),
                "language": item.get("language", ""),
            }
            for item in data.get("items", [])[:max_results]
        ]

    except Exception as exc:
        logger.warning("GitHub search failed: %s", exc)
        return []
