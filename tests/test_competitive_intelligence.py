# tests/test_competitive_intelligence.py
"""Tests for S1 Competitive Intelligence Loop.

Covers:
- github_release_watcher: new release detection + signal extraction
- community_scanner: HN + Reddit fetch + signal write
- ace_competitor_matrix: capability matrix MCP tool
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_pool():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[])
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn
    return mock_p, mock_db


# ── github_release_watcher: _extract_owner_repo ───────────────────────────────


def test_extract_owner_repo_github_source():
    from core.engine.sentinel.engines.github_release_watcher import _extract_owner_repo

    sources = [{"type": "github", "url": "https://github.com/paul-gauthier/aider"}]
    assert _extract_owner_repo(sources) == "paul-gauthier/aider"


def test_extract_owner_repo_releases_source():
    from core.engine.sentinel.engines.github_release_watcher import _extract_owner_repo

    sources = [{"type": "releases", "url": "https://github.com/cline/cline/releases"}]
    assert _extract_owner_repo(sources) == "cline/cline"


def test_extract_owner_repo_no_github():
    from core.engine.sentinel.engines.github_release_watcher import _extract_owner_repo

    sources = [{"type": "changelog", "url": "https://cursor.com/changelog"}]
    assert _extract_owner_repo(sources) is None


def test_extract_owner_repo_empty():
    from core.engine.sentinel.engines.github_release_watcher import _extract_owner_repo

    assert _extract_owner_repo([]) is None


# ── github_release_watcher: fetch_latest_release ─────────────────────────────


@pytest.mark.asyncio
async def test_fetch_latest_release_success():
    from core.engine.sentinel.engines.github_release_watcher import fetch_latest_release

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"tag_name": "v1.2.0", "name": "Release 1.2", "body": "Bug fixes"}
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_latest_release("paul-gauthier/aider")

    assert result["tag_name"] == "v1.2.0"


@pytest.mark.asyncio
async def test_fetch_latest_release_404():
    from core.engine.sentinel.engines.github_release_watcher import fetch_latest_release

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_latest_release("nonexistent/repo")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_latest_release_network_error():
    from core.engine.sentinel.engines.github_release_watcher import fetch_latest_release

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_latest_release("some/repo")

    assert result is None


# ── github_release_watcher: run_github_release_watcher ───────────────────────


@pytest.mark.asyncio
async def test_github_release_watcher_no_competitors(mock_pool):
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])  # no competitors

    from core.engine.sentinel.engines import github_release_watcher

    with patch.object(github_release_watcher, "pool", mock_p):
        result = await github_release_watcher.run_github_release_watcher("product:platform")

    assert result["competitors_checked"] == 0
    assert result["new_releases"] == 0


@pytest.mark.asyncio
async def test_github_release_watcher_skips_same_tag(mock_pool):
    """Competitor with same stored + latest tag → no new release, no signals."""
    from core.engine.sentinel.engines import github_release_watcher  # import before patching

    mock_p, mock_db = mock_pool
    comp_rows = [
        {
            "id": "competitor:aider",
            "name": "Aider",
            "tier": 1,
            "sources": [{"type": "github", "url": "https://github.com/paul-gauthier/aider"}],
            "last_release_tag": "v0.82.0",
        }
    ]
    mock_db.query = AsyncMock(return_value=comp_rows)

    release = {"tag_name": "v0.82.0", "name": "v0.82.0", "body": ""}

    with (
        patch.object(github_release_watcher, "pool", mock_p),
        patch.object(github_release_watcher, "fetch_latest_release", return_value=release),
    ):
        result = await github_release_watcher.run_github_release_watcher("product:platform")

    assert result["new_releases"] == 0
    assert result["competitors_checked"] == 1


@pytest.mark.asyncio
async def test_github_release_watcher_detects_new_release(mock_pool):
    """New tag differs from stored → signals extracted and written."""
    from core.engine.sentinel.engines import github_release_watcher  # import before patching

    mock_p, mock_db = mock_pool
    comp_rows = [
        {
            "id": "competitor:aider",
            "name": "Aider",
            "tier": 1,
            "sources": [{"type": "github", "url": "https://github.com/paul-gauthier/aider"}],
            "last_release_tag": "v0.81.0",
        }
    ]
    mock_db.query = AsyncMock(return_value=comp_rows)

    release = {
        "tag_name": "v0.82.0",
        "name": "v0.82.0",
        "body": "Added voice control and multi-file editing",
        "html_url": "https://github.com/paul-gauthier/aider/releases/tag/v0.82.0",
    }
    fake_signal = {
        "title": "Multi-file editing",
        "description": "Aider now edits multiple files at once",
        "relevance": "threat",
        "urgency": "high",
        "relevance_score": 0.85,
        "action": "respond",
        "rationale": "We don't have this",
        "competitor": "Aider",
    }

    with (
        patch.object(github_release_watcher, "pool", mock_p),
        patch.object(github_release_watcher, "fetch_latest_release", return_value=release),
        patch.object(github_release_watcher, "extract_signals", return_value=[fake_signal]),
        patch.object(github_release_watcher, "classify_signal", return_value=fake_signal),
    ):
        result = await github_release_watcher.run_github_release_watcher("product:platform")

    assert result["new_releases"] == 1
    assert result["signals_extracted"] == 1


# ── community_scanner: _fetch_hn_posts ────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_hn_posts_returns_titles():
    from core.engine.sentinel.engines.community_scanner import _fetch_hn_posts

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "hits": [
            {"title": "Cursor AI is amazing", "objectID": "1"},
            {"title": "Why I switched from Cursor to X", "objectID": "2"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_c = AsyncMock()
        mock_c.get = AsyncMock(return_value=mock_resp)
        mock_c.__aenter__ = AsyncMock(return_value=mock_c)
        mock_c.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_c

        posts = await _fetch_hn_posts("Cursor")

    assert len(posts) == 2
    assert "Cursor AI is amazing" in posts[0]


@pytest.mark.asyncio
async def test_fetch_hn_posts_handles_error():
    from core.engine.sentinel.engines.community_scanner import _fetch_hn_posts

    with patch("httpx.AsyncClient") as mock_cls:
        mock_c = AsyncMock()
        mock_c.get = AsyncMock(side_effect=Exception("timeout"))
        mock_c.__aenter__ = AsyncMock(return_value=mock_c)
        mock_c.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_c

        posts = await _fetch_hn_posts("Cursor")

    assert posts == []


# ── community_scanner: run_community_scanner ─────────────────────────────────


@pytest.mark.asyncio
async def test_community_scanner_no_tier1_competitors(mock_pool):
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    from core.engine.sentinel.engines import community_scanner

    with patch.object(community_scanner, "pool", mock_p):
        result = await community_scanner.run_community_scanner("product:platform")

    assert result["competitors_scanned"] == 0
    assert result["signals_extracted"] == 0


@pytest.mark.asyncio
async def test_community_scanner_extracts_signals(mock_pool):
    from core.engine.sentinel.engines import community_scanner  # import before patching

    mock_p, mock_db = mock_pool
    comp_rows = [{"id": "competitor:cursor", "name": "Cursor", "tier": 1, "sources": [], "product": "product:platform"}]
    mock_db.query = AsyncMock(return_value=comp_rows)

    fake_signal = {
        "title": "Users frustrated with latency",
        "description": "Community posts show users unhappy with response time",
        "relevance": "opportunity",
        "urgency": "medium",
        "relevance_score": 0.7,
        "action": "respond",
        "rationale": "We can win here with faster responses",
        "competitor": "Cursor",
    }

    with (
        patch.object(community_scanner, "pool", mock_p),
        patch.object(community_scanner, "_fetch_hn_posts", return_value=["HN | Cursor slow"]),
        patch.object(community_scanner, "_fetch_reddit_posts", return_value=[]),
        patch.object(community_scanner, "extract_signals", return_value=[fake_signal]),
        patch.object(community_scanner, "classify_signal", return_value=fake_signal),
    ):
        result = await community_scanner.run_community_scanner("product:platform")

    assert result["competitors_scanned"] == 1
    assert result["signals_extracted"] == 1


# ── ace_competitor_matrix ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ace_competitor_matrix_empty(mock_pool):
    mock_p, mock_db = mock_pool
    mock_db.query = AsyncMock(return_value=[])

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_competitor_matrix(product_id="product:platform")

    assert result["matrix"] == {}
    assert result["differentiation"] == []
    assert result["total_entries"] == 0


@pytest.mark.asyncio
async def test_ace_competitor_matrix_builds_nested_dict(mock_pool):
    mock_p, mock_db = mock_pool
    rows = [
        {"competitor": "Cursor", "capability_slug": "multi_file_editing", "coverage": "full"},
        {"competitor": "Cursor", "capability_slug": "decision_capture", "coverage": "none"},
        {"competitor": "Aider", "capability_slug": "multi_file_editing", "coverage": "partial"},
        {"competitor": "Aider", "capability_slug": "decision_capture", "coverage": "none"},
    ]
    mock_db.query = AsyncMock(return_value=rows)

    from core.engine.mcp import tools

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_competitor_matrix(product_id="product:platform")

    assert result["matrix"]["Cursor"]["multi_file_editing"] == "full"
    assert result["matrix"]["Aider"]["multi_file_editing"] == "partial"
    assert sorted(result["competitors"]) == ["Aider", "Cursor"]


@pytest.mark.asyncio
async def test_ace_competitor_matrix_differentiation():
    """Capabilities where no competitor has 'full' coverage are differentiation."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.mcp import tools

    rows = [
        {"competitor": "Cursor", "capability_slug": "code_completion", "coverage": "full"},
        {"competitor": "Cursor", "capability_slug": "intelligence_briefing", "coverage": "none"},
        {"competitor": "Aider", "capability_slug": "code_completion", "coverage": "partial"},
        {"competitor": "Aider", "capability_slug": "intelligence_briefing", "coverage": "none"},
    ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=rows)
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_p = MagicMock()
    mock_p.connection.return_value = mock_conn

    with patch.object(tools, "pool", mock_p):
        result = await tools.ace_competitor_matrix(product_id="product:platform")

    # code_completion: Cursor has "full" → not differentiation
    # intelligence_briefing: nobody has "full" → differentiation
    assert "intelligence_briefing" in result["differentiation"]
    assert "code_completion" not in result["differentiation"]
