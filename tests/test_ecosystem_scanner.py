"""Tests for ecosystem scanner sentinel engine."""

from unittest.mock import AsyncMock

import pytest


def _fires_on(cron: str) -> set[str]:
    """The days a cron ACTUALLY fires, in APScheduler's reading of it.

    Asserting the cron STRING is the weak form and it is how this bug lived: the old
    assertion here was `== "0 5 * * 0"  # Sunday 5 AM`, which passed for months while the
    engine ran on MONDAY. APScheduler reads day-of-week 0=mon..6=sun, not the standard
    crontab 0=sun, and does not translate. Assert the behaviour, not the literal.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    tz = ZoneInfo("UTC")
    trigger = CronTrigger.from_crontab(cron, timezone=tz)
    days, prev = set(), datetime(2026, 7, 12, tzinfo=tz)  # a Sunday
    for _ in range(7):
        nxt = trigger.get_next_fire_time(None, prev)
        days.add(nxt.strftime("%A"))
        prev = nxt.replace(hour=23, minute=59)
    return days


def test_extract_url_basic():
    from core.engine.sentinel.engines.ecosystem_scanner import _extract_url

    assert _extract_url("Check https://github.com/foo/bar for details") == "https://github.com/foo/bar"


def test_extract_url_strips_trailing_punctuation():
    from core.engine.sentinel.engines.ecosystem_scanner import _extract_url

    assert _extract_url("(https://example.com/path),") == "https://example.com/path"


def test_extract_url_returns_none():
    from core.engine.sentinel.engines.ecosystem_scanner import _extract_url

    assert _extract_url("no urls here") is None


@pytest.mark.asyncio
async def test_build_seen_urls():
    """Builds seen set from research_queue + experiment_log entries."""
    from core.engine.sentinel.engines.ecosystem_scanner import _build_seen_urls

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            [[{"context": "[ecosystem-discovery] foo (https://github.com/foo/bar)\nStars: 100"}]],
            [[{"url": "https://github.com/baz/qux"}]],
        ]
    )

    seen = await _build_seen_urls(mock_db, "product:test")
    assert "https://github.com/foo/bar" in seen
    assert "https://github.com/baz/qux" in seen


@pytest.mark.asyncio
async def test_build_seen_urls_handles_empty():
    """Empty DB results → empty set, no crash."""
    from core.engine.sentinel.engines.ecosystem_scanner import _build_seen_urls

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    seen = await _build_seen_urls(mock_db, "product:test")
    assert seen == set()


@pytest.mark.asyncio
async def test_scan_specialties_generates_queries_and_scores():
    """Mock DB returns 1 active specialty; LLM generates queries then scores.

    Assert 1 specialty scanned, 1 relevant finding (0.85 score passes threshold),
    2 LLM calls.
    """
    from core.engine.sentinel.engines.ecosystem_scanner import _scan_specialties

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # Query 1: active specialties
            [
                [
                    {
                        "id": "specialty:llm-eng",
                        "slug": "llm-engineering",
                        "description": "LLM engineering practices",
                        "perspective": "practitioner",
                        "discipline_slug": "engineering",
                        "task_count": 25,
                    }
                ]
            ],
            # Query 2: insights for the specialty
            [[{"content": "Use structured outputs for reliability"}]],
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        side_effect=[
            # LLM call 1: query generation
            ["structured output libraries python", "pydantic llm validation 2025"],
            # LLM call 2: relevance scoring
            [{"relevance": 0.85, "reason": "Directly relevant", "integration_angle": "Use as validation layer"}],
        ]
    )

    async def fake_github_search(query, max_results=5, min_stars=50):
        return [
            {
                "name": "instructor",
                "url": "https://github.com/jxnl/instructor",
                "description": "Structured outputs for LLMs",
                "stars": 8000,
                "updated_at": "2025-01-01",
                "topics": ["llm", "pydantic"],
                "language": "Python",
            }
        ]

    async def fake_web_search(query, max_results=3):
        return []

    stats = await _scan_specialties(
        mock_db,
        mock_llm,
        "product:test",
        set(),
        github_search_fn=fake_github_search,
        web_search_fn=fake_web_search,
    )

    assert stats["specialties_scanned"] == 1
    assert stats["relevant_findings"] == 1
    assert stats["llm_calls"] == 2
    assert len(stats["to_queue"]) == 1
    assert stats["to_queue"][0]["specialty_slug"] == "llm-engineering"


@pytest.mark.asyncio
async def test_scan_specialties_handles_malformed_llm():
    """LLM returns dict instead of array for query gen, string for scoring.

    Assert no crash, 0 relevant findings.
    """
    from core.engine.sentinel.engines.ecosystem_scanner import _scan_specialties

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # Query 1: active specialties
            [
                [
                    {
                        "id": "specialty:bad",
                        "slug": "bad-specialty",
                        "description": "A specialty",
                        "perspective": "practitioner",
                        "discipline_slug": "engineering",
                        "task_count": 15,
                    }
                ]
            ],
            # Query 2: insights
            [[]],
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        side_effect=[
            # LLM call 1: malformed — returns dict instead of list
            {"error": "oops", "queries": ["some query"]},
            # LLM call 2: malformed — returns string instead of list
            "not a list at all",
        ]
    )

    async def fake_github_search(query, max_results=5, min_stars=50):
        return [
            {
                "name": "some-lib",
                "url": "https://github.com/example/some-lib",
                "description": "A library",
                "stars": 200,
                "updated_at": "2025-01-01",
                "topics": [],
                "language": "Python",
            }
        ]

    async def fake_web_search(query, max_results=3):
        return []

    stats = await _scan_specialties(
        mock_db,
        mock_llm,
        "product:test",
        set(),
        github_search_fn=fake_github_search,
        web_search_fn=fake_web_search,
    )

    assert stats["relevant_findings"] == 0
    assert stats["specialties_scanned"] == 1


@pytest.mark.asyncio
async def test_scan_workspaces():
    """Workspace scan loads workspace + specialties, generates queries, scores."""
    from core.engine.sentinel.engines.ecosystem_scanner import _scan_workspaces

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # workspaces
            [
                [
                    {
                        "name": "ACE Platform",
                        "active_domains": ["technology"],
                        "tools": ["surrealdb", "claude"],
                        "vocabulary": {"IPM": "insight-per-message"},
                    }
                ]
            ],
            # active specialties for context
            [
                [
                    {
                        "slug": "llm-engineering",
                        "description": "LLM eng",
                        "perspective": "practitioner",
                        "discipline": "engineering",
                    }
                ]
            ],
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        side_effect=[
            ["knowledge graph temporal memory"],  # queries
            [{"relevance": 0.9, "reason": "Direct fit", "integration_angle": "Replace current graph"}],
        ]
    )

    async def fake_github(query, **kw):
        return [
            {
                "name": "o/graphiti",
                "url": "https://github.com/o/graphiti",
                "description": "Temporal knowledge graph",
                "stars": 2000,
                "updated_at": "2026-03-15",
                "topics": ["graph"],
                "language": "Python",
            }
        ]

    seen: set[str] = set()

    findings = await _scan_workspaces(
        mock_db,
        mock_llm,
        "product:test",
        seen,
        github_search_fn=fake_github,
        web_search_fn=AsyncMock(return_value=[]),
    )

    assert findings["workspaces_scanned"] == 1
    assert findings["relevant_findings"] == 1
    assert findings["llm_calls"] == 2


def test_engine_registration():
    """Ecosystem scanner is registered with correct cron."""
    from core.engine.sentinel.engines.ecosystem_scanner import run_ecosystem_scanner  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "ecosystem_scanner" in engine_registry
    assert _fires_on(engine_registry["ecosystem_scanner"]["cron"]) == {"Tuesday"}


@pytest.mark.asyncio
async def test_full_run_queues_findings():
    """Integration: full engine run discovers, scores, dedup, queues."""
    from unittest.mock import patch

    from core.engine.sentinel.engines import ecosystem_scanner

    mock_db = AsyncMock()
    queued_items = []

    async def mock_query(query_str, params=None):
        q = query_str.strip()
        if "research_queue" in q and "source = 'ecosystem-scanner'" in q:
            return [[]]
        if "experiment_log" in q:
            return [[]]
        if "FROM specialty" in q and "task_count >= 10" in q:
            return [
                [
                    {
                        "id": "specialty:s1",
                        "slug": "s1",
                        "description": "Test spec",
                        "perspective": "practitioner",
                        "discipline_slug": "engineering",
                        "task_count": 15,
                    }
                ]
            ]
        if "FROM insight" in q:
            return [[{"content": "Use X for Y"}]]
        if "FROM workspace" in q:
            return [[]]
        if "bootstrapped = true" in q:
            return [[]]
        if "CREATE research_queue" in q:
            queued_items.append(params)
            return [{"id": "research_queue:abc"}]
        return [[]]

    mock_db.query = AsyncMock(side_effect=mock_query)

    with (
        patch.object(ecosystem_scanner, "pool") as mock_pool,
        patch.object(ecosystem_scanner, "llm") as mock_llm,
        patch.object(ecosystem_scanner, "github_search", new_callable=AsyncMock) as mock_gh,
        patch.object(ecosystem_scanner, "web_search", new_callable=AsyncMock) as mock_web,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_llm.complete_json = AsyncMock(
            side_effect=[
                ["query1"],
                [{"relevance": 0.85, "reason": "Good", "integration_angle": "Use it"}],
            ]
        )

        mock_gh.return_value = [
            {
                "name": "o/tool",
                "url": "https://github.com/o/tool",
                "description": "Useful tool",
                "stars": 300,
                "updated_at": "2026-03-01",
                "topics": [],
                "language": "Python",
            }
        ]
        mock_web.return_value = []

        result = await ecosystem_scanner.run_ecosystem_scanner("product:test")

    assert result["specialties_scanned"] == 1
    assert result["queued"] == 1
    assert result["llm_calls"] == 2
    assert len(queued_items) == 1
