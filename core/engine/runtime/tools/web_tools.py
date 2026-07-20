"""Web tools — search, research, extraction, and GitHub API access.

All tools use httpx (already a core dependency) for REST calls.
API keys are read from environment variables at execute time — missing
keys fall through to the next backend gracefully.

Tool list:
  web_search     — Tavily → Brave → DDG priority chain (broad search)
  web_research   — Exa semantic/neural search (deep retrieval)
  web_extract    — Firecrawl (self-hosted) → Jina Reader fallback
  github_search  — GitHub issues, PRs, code, repo search
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from core.engine.core.config import settings
from core.engine.runtime.tools import RuntimeTool

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0  # seconds for all web calls

try:
    from ddgs import DDGS as _DDGS  # type: ignore[import-untyped]

    _DDG_AVAILABLE = True
except ImportError:
    _DDGS = None  # type: ignore[assignment]
    _DDG_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_chars: int = 500) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _fmt_results(results: list[dict]) -> str:
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", r.get("href", ""))
        snippet = _truncate(r.get("content", r.get("body", r.get("description", ""))), 400)
        lines.append(f"{i}. {title}\n   {url}\n   {snippet}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# WebSearchTool — Tavily → Brave → DDG
# ---------------------------------------------------------------------------


class WebSearchTool(RuntimeTool):
    """Broad web search via Tavily (primary), Brave, or DuckDuckGo fallback."""

    name: str = "web_search"
    description: str = (
        "Search the web for current information. Uses Tavily, Brave, or DuckDuckGo — "
        "whichever is available. Good for factual lookups, news, documentation, and "
        "finding solutions to specific problems."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return. Defaults to 10.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        query: str = input["query"]
        max_results: int = int(input.get("max_results", 10))

        # Try Tavily first
        tavily_key = os.environ.get("TAVILY_API_KEY", "")
        if tavily_key:
            try:
                return await self._tavily(query, max_results, tavily_key)
            except Exception as exc:
                logger.debug("Tavily failed, trying Brave: %s", exc)

        # Try Brave
        brave_key = os.environ.get("BRAVE_API_KEY", "")
        if brave_key:
            try:
                return await self._brave(query, max_results, brave_key)
            except Exception as exc:
                logger.debug("Brave failed, trying DDG: %s", exc)

        # Fall back to DDG
        if _DDG_AVAILABLE:
            try:
                return self._ddg(query, max_results)
            except Exception as exc:
                logger.debug("DDG failed: %s", exc)
                return f"All search backends failed. Last error: {exc}"

        return (
            "No search backend available. Set TAVILY_API_KEY or BRAVE_API_KEY, "
            "or install duckduckgo-search: pip install 'ace[search]'"
        )

    async def _tavily(self, query: str, max_results: int, api_key: str) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in data.get("results", [])
        ]
        return f"[Tavily]\n\n{_fmt_results(results)}"

    async def _brave(self, query: str, max_results: int, api_key: str) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
        raw = data.get("web", {}).get("results", [])
        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("description", "")} for r in raw
        ]
        return f"[Brave]\n\n{_fmt_results(results)}"

    def _ddg(self, query: str, max_results: int) -> str:
        results = list(_DDGS().text(query, max_results=max_results))
        formatted = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")} for r in results
        ]
        return f"[DuckDuckGo]\n\n{_fmt_results(formatted)}"


# ---------------------------------------------------------------------------
# WebResearchTool — Exa semantic/neural search
# ---------------------------------------------------------------------------


class WebResearchTool(RuntimeTool):
    """Deep semantic search via Exa — better for research, exemplar repos, concepts."""

    name: str = "web_research"
    description: str = (
        "Semantic neural search via Exa. Better than keyword search for finding "
        "exemplar repos, concepts, conventions, and 'how should WE do X' questions. "
        "Requires EXA_API_KEY."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Research query — use natural language, not keywords.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Results to return. Defaults to 10.",
                },
                "include_text": {
                    "type": "boolean",
                    "description": "Include page text extracts. Defaults to True.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        api_key = os.environ.get("EXA_API_KEY", "")
        if not api_key:
            return "EXA_API_KEY not set. Exa semantic search unavailable."

        query: str = input["query"]
        num_results: int = int(input.get("num_results", 10))
        include_text: bool = bool(input.get("include_text", True))

        payload: dict[str, Any] = {
            "query": query,
            "numResults": num_results,
            "type": "neural",
            "useAutoprompt": True,
        }
        if include_text:
            payload["contents"] = {"text": {"maxCharacters": 1000}}

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.exa.ai/search",
                    json=payload,
                    headers={"x-api-key": api_key, "Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Exa search failed: %s", exc)
            return f"Exa search error: {exc}"

        results = []
        for r in data.get("results", []):
            text = ""
            if include_text and r.get("text"):
                text = _truncate(r["text"], 600)
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": text or r.get("summary", ""),
                }
            )
        return f"[Exa]\n\n{_fmt_results(results)}"


# ---------------------------------------------------------------------------
# WebExtractTool — Firecrawl → Jina Reader
# ---------------------------------------------------------------------------


class WebExtractTool(RuntimeTool):
    """Extract full page content from a URL. Firecrawl (self-hosted) or Jina fallback."""

    name: str = "web_extract"
    description: str = (
        "Extract the full readable content from a URL. Returns markdown. "
        "Uses Firecrawl (self-hosted, handles JS) if FIRECRAWL_URL is set, "
        "otherwise falls back to Jina Reader (static pages only)."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to extract content from.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return. Defaults to 8000.",
                },
            },
            "required": ["url"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        url: str = input["url"]
        max_chars: int = int(input.get("max_chars", 8000))

        # Try Firecrawl (self-hosted)
        firecrawl_url = os.environ.get("FIRECRAWL_URL", "").rstrip("/")
        if firecrawl_url:
            try:
                return await self._firecrawl(url, firecrawl_url, max_chars)
            except Exception as exc:
                logger.debug("Firecrawl failed, falling back to Jina: %s", exc)

        # Fall back to Jina Reader
        try:
            return await self._jina(url, max_chars)
        except Exception as exc:
            logger.warning("Jina extraction failed: %s", exc)
            return f"Extraction failed: {exc}"

    async def _firecrawl(self, url: str, base_url: str, max_chars: int) -> str:
        api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/v1/scrape",
                json={"url": url, "formats": ["markdown"]},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        content = data.get("data", {}).get("markdown", "") or data.get("markdown", "")
        return f"[Firecrawl] {url}\n\n{content[:max_chars]}"

    async def _jina(self, url: str, max_chars: int) -> str:
        jina_url = f"https://r.jina.ai/{url}"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers={"Accept": "text/plain"})
            resp.raise_for_status()
        return f"[Jina] {url}\n\n{resp.text[:max_chars]}"


# ---------------------------------------------------------------------------
# GitHubSearchTool
# ---------------------------------------------------------------------------


class GitHubSearchTool(RuntimeTool):
    """Search GitHub for repos, code, issues, and PRs."""

    name: str = "github_search"
    description: str = (
        "Search GitHub for repositories, code examples, issues, and pull requests. "
        "Better than web search for finding how quality codebases solve a problem. "
        "Uses GITHUB_TOKEN if set (higher rate limits)."
    )
    is_read_only: bool = True

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Use GitHub search syntax (e.g. 'async context manager language:python').",
                },
                "search_type": {
                    "type": "string",
                    "description": "What to search. One of: repositories, code, issues, commits. Defaults to repositories.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Results to return. Defaults to 10.",
                },
            },
            "required": ["query"],
        }

    async def execute(self, input: dict[str, Any]) -> str:
        query: str = input["query"]
        search_type: str = input.get("search_type", "repositories")
        max_results: int = int(input.get("max_results", 10))

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = settings.github_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        valid_types = {"repositories", "code", "issues", "commits"}
        if search_type not in valid_types:
            search_type = "repositories"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    f"https://api.github.com/search/{search_type}",
                    params={"q": query, "per_page": max_results},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("GitHub search failed: %s", exc)
            return f"GitHub search error: {exc}"

        items = data.get("items", [])
        if not items:
            return "No GitHub results found."

        lines = []
        for item in items:
            if search_type == "repositories":
                lines.append(
                    f"- {item.get('full_name', '')} ★{item.get('stargazers_count', 0)}\n"
                    f"  {item.get('html_url', '')}\n"
                    f"  {_truncate(item.get('description', '') or '', 200)}"
                )
            elif search_type == "code":
                lines.append(
                    f"- {item.get('repository', {}).get('full_name', '')}: {item.get('path', '')}\n"
                    f"  {item.get('html_url', '')}"
                )
            elif search_type == "issues":
                lines.append(
                    f"- [{item.get('state', '')}] {item.get('title', '')}\n"
                    f"  {item.get('html_url', '')}\n"
                    f"  {_truncate(item.get('body', '') or '', 200)}"
                )
            elif search_type == "commits":
                lines.append(
                    f"- {item.get('sha', '')[:8]} {item.get('commit', {}).get('message', '')[:100]}\n"
                    f"  {item.get('html_url', '')}"
                )

        return f"[GitHub {search_type}]\n\n" + "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_web_tools() -> list[RuntimeTool]:
    """Return all web tools, ready to register."""
    return [
        WebSearchTool(),
        WebResearchTool(),
        WebExtractTool(),
        GitHubSearchTool(),
    ]
