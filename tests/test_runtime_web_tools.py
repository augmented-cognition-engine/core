"""Tests for web tools — search, research, extraction, GitHub."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.engine.runtime.tools.web_tools import (
    GitHubSearchTool,
    WebExtractTool,
    WebResearchTool,
    WebSearchTool,
    make_web_tools,
)

# ---------------------------------------------------------------------------
# Schema / metadata
# ---------------------------------------------------------------------------


def test_make_web_tools_returns_four():
    tools = make_web_tools()
    assert len(tools) == 4


def test_all_web_tools_are_read_only():
    for tool in make_web_tools():
        assert tool.is_read_only, f"{tool.name} should be read-only"


def test_all_have_required_fields():
    for tool in make_web_tools():
        assert tool.name
        assert tool.description
        schema = tool.to_api_schema()
        assert "input_schema" in schema


def test_web_search_requires_query():
    tool = WebSearchTool()
    assert "query" in tool.get_input_schema()["required"]


def test_web_research_requires_query():
    tool = WebResearchTool()
    assert "query" in tool.get_input_schema()["required"]


def test_web_extract_requires_url():
    tool = WebExtractTool()
    assert "url" in tool.get_input_schema()["required"]


def test_github_search_requires_query():
    tool = GitHubSearchTool()
    assert "query" in tool.get_input_schema()["required"]


# ---------------------------------------------------------------------------
# WebSearchTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_search_uses_tavily_when_key_set():
    tool = WebSearchTool()
    tavily_resp = {"results": [{"title": "Result 1", "url": "https://example.com", "content": "test content"}]}

    mock_response = MagicMock()
    mock_response.json.return_value = tavily_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key", "BRAVE_API_KEY": ""}):
            result = await tool.execute({"query": "python async patterns"})

    assert "Tavily" in result
    assert "Result 1" in result or "example.com" in result


@pytest.mark.asyncio
async def test_web_search_falls_back_to_brave_if_tavily_fails():
    tool = WebSearchTool()
    brave_resp = {
        "web": {"results": [{"title": "Brave Result", "url": "https://brave.com", "description": "brave desc"}]}
    }

    mock_response = MagicMock()
    mock_response.json.return_value = brave_resp
    mock_response.raise_for_status = MagicMock()

    call_count = 0

    async def side_effect_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.HTTPStatusError("tavily error", request=MagicMock(), response=MagicMock())
        return mock_response

    async def side_effect_get(*args, **kwargs):
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = side_effect_post
    mock_client.get = side_effect_get

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"TAVILY_API_KEY": "bad-key", "BRAVE_API_KEY": "brave-key"}):
            result = await tool.execute({"query": "test"})

    assert "Brave" in result


@pytest.mark.asyncio
async def test_web_search_no_backends_returns_helpful_message():
    tool = WebSearchTool()
    with patch.dict("os.environ", {"TAVILY_API_KEY": "", "BRAVE_API_KEY": ""}):
        with patch("core.engine.runtime.tools.web_tools._DDG_AVAILABLE", False):
            result = await tool.execute({"query": "test"})
    assert "No search backend" in result or "not available" in result.lower()


@pytest.mark.asyncio
async def test_web_search_uses_ddg_when_no_keys():
    tool = WebSearchTool()
    ddg_results = [{"title": "DDG Result", "href": "https://ddg.com", "body": "ddg body"}]

    mock_ddg_class = MagicMock()
    mock_ddg_instance = MagicMock()
    mock_ddg_instance.text.return_value = ddg_results
    mock_ddg_class.return_value = mock_ddg_instance

    import core.engine.runtime.tools.web_tools as web_mod

    with patch.dict("os.environ", {"TAVILY_API_KEY": "", "BRAVE_API_KEY": ""}):
        with patch.object(web_mod, "_DDG_AVAILABLE", True):
            with patch.object(web_mod, "_DDGS", mock_ddg_class, create=True):
                result = await tool.execute({"query": "test"})

    assert "DuckDuckGo" in result
    assert "DDG Result" in result


# ---------------------------------------------------------------------------
# WebResearchTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_research_no_key_returns_message():
    tool = WebResearchTool()
    with patch.dict("os.environ", {"EXA_API_KEY": ""}):
        result = await tool.execute({"query": "best testing patterns"})
    assert "EXA_API_KEY" in result


@pytest.mark.asyncio
async def test_web_research_calls_exa_api():
    tool = WebResearchTool()
    exa_resp = {
        "results": [{"title": "pytest best practices", "url": "https://docs.pytest.org", "text": "use fixtures"}]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = exa_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}):
            result = await tool.execute({"query": "pytest best practices"})

    assert "Exa" in result
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "api.exa.ai" in call_args[0][0]


@pytest.mark.asyncio
async def test_web_research_handles_error():
    tool = WebResearchTool()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"EXA_API_KEY": "test-key"}):
            result = await tool.execute({"query": "test"})

    assert "error" in result.lower()


# ---------------------------------------------------------------------------
# WebExtractTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_extract_uses_firecrawl_when_configured():
    tool = WebExtractTool()
    firecrawl_resp = {"data": {"markdown": "# Page Title\n\nSome content here."}}

    mock_response = MagicMock()
    mock_response.json.return_value = firecrawl_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"FIRECRAWL_URL": "http://localhost:3002"}):
            result = await tool.execute({"url": "https://example.com"})

    assert "Firecrawl" in result
    assert "Page Title" in result


@pytest.mark.asyncio
async def test_web_extract_falls_back_to_jina():
    tool = WebExtractTool()
    jina_content = "# Jina Result\n\nPage content from Jina."

    call_count = 0

    async def post_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.ConnectError("firecrawl down")

    mock_get_response = MagicMock()
    mock_get_response.text = jina_content
    mock_get_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = post_side_effect
    mock_client.get = AsyncMock(return_value=mock_get_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"FIRECRAWL_URL": "http://localhost:3002"}):
            result = await tool.execute({"url": "https://example.com"})

    assert "Jina" in result
    assert "Jina Result" in result


@pytest.mark.asyncio
async def test_web_extract_uses_jina_when_no_firecrawl():
    tool = WebExtractTool()

    mock_get_response = MagicMock()
    mock_get_response.text = "page content"
    mock_get_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_get_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"FIRECRAWL_URL": ""}):
            result = await tool.execute({"url": "https://example.com"})

    assert "Jina" in result


@pytest.mark.asyncio
async def test_web_extract_respects_max_chars():
    tool = WebExtractTool()
    long_content = "x" * 20000

    mock_get_response = MagicMock()
    mock_get_response.text = long_content
    mock_get_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_get_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"FIRECRAWL_URL": ""}):
            result = await tool.execute({"url": "https://example.com", "max_chars": 500})

    # Header + content should be < 600 chars total
    content_part = result.split("\n\n", 1)[1] if "\n\n" in result else result
    assert len(content_part) <= 500


# ---------------------------------------------------------------------------
# GitHubSearchTool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_search_repositories():
    tool = GitHubSearchTool()
    gh_resp = {
        "items": [
            {
                "full_name": "django/django",
                "stargazers_count": 70000,
                "html_url": "https://github.com/django/django",
                "description": "The Web framework for perfectionists with deadlines.",
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = gh_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            result = await tool.execute({"query": "async ORM python", "search_type": "repositories"})

    assert "GitHub repositories" in result
    assert "django/django" in result
    assert "70000" in result


@pytest.mark.asyncio
async def test_github_search_code():
    tool = GitHubSearchTool()
    gh_resp = {
        "items": [
            {
                "repository": {"full_name": "django/django"},
                "path": "django/db/models/base.py",
                "html_url": "https://github.com/django/django/blob/main/django/db/models/base.py",
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.json.return_value = gh_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch("core.engine.runtime.tools.web_tools.settings") as mock_settings:
            mock_settings.github_token = "test-token"
            result = await tool.execute({"query": "async def save", "search_type": "code"})

    assert "GitHub code" in result
    call_kwargs = mock_client.get.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_github_search_invalid_type_defaults_to_repositories():
    tool = GitHubSearchTool()
    gh_resp = {"items": []}

    mock_response = MagicMock()
    mock_response.json.return_value = gh_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {"GITHUB_TOKEN": ""}):
            result = await tool.execute({"query": "test", "search_type": "invalid_type"})

    call_args = mock_client.get.call_args[0][0]
    assert "repositories" in call_args


@pytest.mark.asyncio
async def test_github_search_no_results():
    tool = GitHubSearchTool()
    gh_resp = {"items": []}

    mock_response = MagicMock()
    mock_response.json.return_value = gh_resp
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("core.engine.runtime.tools.web_tools.httpx.AsyncClient", return_value=mock_client):
        result = await tool.execute({"query": "no results here xyz123"})

    assert "No GitHub results" in result


# ---------------------------------------------------------------------------
# Runtime registration
# ---------------------------------------------------------------------------


def test_runtime_registers_web_tools():
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)
    names = rt.tool_names
    assert "web_search" in names
    assert "web_research" in names
    assert "web_extract" in names
    assert "github_search" in names


def test_runtime_total_tool_count_with_intelligence():
    """6 built-in + 15 ACE + 4 web + 1 browser = 26 total."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=True, product_id="product:test")
    assert len(rt.tool_names) == 26


def test_runtime_total_tool_count_without_intelligence():
    """6 built-in + 4 web + 1 browser = 11 total."""
    from core.engine.runtime.model_adapter import MockAdapter
    from core.engine.runtime.runtime import Runtime

    rt = Runtime(adapter=MockAdapter(responses=[]), enable_intelligence=False)
    assert len(rt.tool_names) == 11
