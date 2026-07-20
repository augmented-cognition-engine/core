# tests/test_github_search.py
"""Tests for github_search() — ecosystem scanner GitHub integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

SAMPLE_ITEM = {
    "full_name": "anthropics/claude",
    "html_url": "https://github.com/anthropics/claude",
    "description": "Claude AI assistant",
    "stargazers_count": 1234,
    "pushed_at": "2026-03-01T12:00:00Z",
    "topics": ["ai", "llm"],
    "language": "Python",
}

SAMPLE_RESPONSE = {"items": [SAMPLE_ITEM], "total_count": 1}


def _make_mock_client(status_code=200, json_data=None, headers=None):
    """Build a mock httpx.AsyncClient context manager."""
    if json_data is None:
        json_data = SAMPLE_RESPONSE
    if headers is None:
        headers = {"X-RateLimit-Remaining": "59"}

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=json_data)
    mock_resp.headers = headers

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return mock_client


@pytest.mark.asyncio
async def test_returns_empty_without_token():
    """No github_token configured → returns empty list immediately."""
    from core.engine.core.search import github_search

    mock_settings = MagicMock()
    mock_settings.github_token = ""

    with patch("core.engine.core.search.settings", mock_settings):
        result = await github_search("machine learning")

    assert result == []


@pytest.mark.asyncio
async def test_parses_github_response():
    """Maps GitHub API fields to our {name, url, description, stars, updated_at, topics, language} schema."""
    from core.engine.core.search import github_search

    mock_settings = MagicMock()
    mock_settings.github_token = "test-token"

    mock_client = _make_mock_client()

    with (
        patch("core.engine.core.search.settings", mock_settings),
        patch("core.engine.core.search.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await github_search("claude")

    assert len(result) == 1
    repo = result[0]
    assert repo["name"] == "anthropics/claude"
    assert repo["url"] == "https://github.com/anthropics/claude"
    assert repo["description"] == "Claude AI assistant"
    assert repo["stars"] == 1234
    assert repo["updated_at"] == "2026-03-01T12:00:00Z"
    assert repo["topics"] == ["ai", "llm"]
    assert repo["language"] == "Python"


@pytest.mark.asyncio
async def test_returns_empty_on_rate_limit():
    """X-RateLimit-Remaining: 0 → returns empty list and logs warning."""
    from core.engine.core.search import github_search

    mock_settings = MagicMock()
    mock_settings.github_token = "test-token"

    mock_client = _make_mock_client(headers={"X-RateLimit-Remaining": "0"})

    with (
        patch("core.engine.core.search.settings", mock_settings),
        patch("core.engine.core.search.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await github_search("claude")

    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_on_exception():
    """HTTP error or network failure → returns empty list, does not raise."""
    from core.engine.core.search import github_search

    mock_settings = MagicMock()
    mock_settings.github_token = "test-token"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("core.engine.core.search.settings", mock_settings),
        patch("core.engine.core.search.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await github_search("claude")

    assert result == []


@pytest.mark.asyncio
async def test_query_construction_with_filters():
    """stars, language, and created_after qualifiers are included in the request params."""
    from core.engine.core.search import github_search

    mock_settings = MagicMock()
    mock_settings.github_token = "test-token"

    mock_client = _make_mock_client()

    with (
        patch("core.engine.core.search.settings", mock_settings),
        patch("core.engine.core.search.httpx.AsyncClient", return_value=mock_client),
    ):
        await github_search(
            "observability",
            max_results=5,
            sort="updated",
            min_stars=200,
            language="Go",
            created_after="2025-01-01",
        )

    call_kwargs = mock_client.get.call_args
    params = call_kwargs.kwargs["params"]

    assert "stars:>=200" in params["q"]
    assert "language:Go" in params["q"]
    assert "created:>=2025-01-01" in params["q"]
    assert "observability" in params["q"]
    assert params["sort"] == "updated"
    assert params["per_page"] == 5


@pytest.mark.asyncio
async def test_handles_missing_fields():
    """Items with None description and missing topics/language fields don't crash."""
    from core.engine.core.search import github_search

    mock_settings = MagicMock()
    mock_settings.github_token = "test-token"

    sparse_item = {
        "full_name": "org/sparse-repo",
        "html_url": "https://github.com/org/sparse-repo",
        "description": None,
        "stargazers_count": 75,
        "pushed_at": "",
        # topics and language intentionally absent
    }
    sparse_response = {"items": [sparse_item], "total_count": 1}

    mock_client = _make_mock_client(json_data=sparse_response)

    with (
        patch("core.engine.core.search.settings", mock_settings),
        patch("core.engine.core.search.httpx.AsyncClient", return_value=mock_client),
    ):
        result = await github_search("sparse")

    assert len(result) == 1
    repo = result[0]
    assert repo["description"] == ""  # None coerced to empty string
    assert repo["topics"] == []  # missing key defaults to []
    assert repo["language"] == ""  # missing key defaults to ""
    assert repo["name"] == "org/sparse-repo"
