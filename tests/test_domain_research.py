# tests/test_domain_research.py
"""Tests for domain research agent — 4-stage experimentation loop."""

from unittest.mock import AsyncMock, patch

import pytest


def test_engine_registration():
    """Domain research engine is registered with correct cron."""
    from core.engine.sentinel.engines.domain_research import run_domain_research  # noqa: F401
    from core.engine.sentinel.registry import engine_registry

    assert "domain_research" in engine_registry
    assert engine_registry["domain_research"]["cron"] == "0 5 * * *"


@pytest.mark.asyncio
async def test_no_active_domains():
    """Returns early when no specialties have enough tasks."""
    from core.engine.sentinel.engines.domain_research import run_domain_research

    with (
        patch("core.engine.sentinel.engines.domain_research.pool") as mock_pool,
        patch(
            "core.engine.sentinel.engines.domain_research._get_eligible_specialties", new_callable=AsyncMock
        ) as mock_eligible,
    ):
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_eligible.return_value = {}

        result = await run_domain_research("product:test")

    assert result["specialties_processed"] == 0


@pytest.mark.asyncio
async def test_research_domain_queries_insights():
    """Research stage queries high-confidence insights and generates search queries."""
    from core.engine.sentinel.engines.domain_research import research_domain

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"content": "Use APCA for contrast", "insight_type": "convention", "confidence": 0.9},
            ]
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(return_value=["APCA latest updates 2026"])

    with patch("core.engine.core.search.web_search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            {
                "title": "APCA Update",
                "url": "https://example.com",
                "snippet": "New APCA changes",
                "relevance_score": 0.8,
            },
        ]
        findings = await research_domain("ux", "product:test", mock_db, mock_llm)

    assert len(findings) >= 1
    assert findings[0]["title"] == "APCA Update"


@pytest.mark.asyncio
async def test_synthesize_generates_tasks():
    """Synthesize stage generates tasks from real task history."""
    from core.engine.sentinel.engines.domain_research import synthesize_test_tasks

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"description": "Build button component with a11y"},
                {"description": "Update token pipeline for dark mode"},
            ]
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value=[
            {
                "description": "Create dialog component",
                "expected_quality_signals": ["uses aria"],
                "discipline": "frontend",
                "complexity": "moderate",
            },
        ]
    )

    tasks = await synthesize_test_tasks("ux", "product:test", 5, mock_db, mock_llm)
    assert len(tasks) == 1
    assert "dialog" in tasks[0]["description"].lower()


@pytest.mark.asyncio
async def test_experiment_runs_ab_test():
    """Experiment stage runs control vs variant and computes statistics."""
    from core.engine.sentinel.engines.domain_research import run_experiment

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            [
                {"content": "Use TypeScript", "insight_type": "convention", "confidence": 0.9},
            ]
        ]
    )

    mock_llm = AsyncMock()
    # Variant generation
    mock_llm.complete_json = AsyncMock(
        return_value={
            "content": "Use strict TypeScript with noUncheckedIndexedAccess",
            "insight_type": "convention",
            "confidence": 0.8,
        }
    )
    # Synthetic task execution (budget LLM)
    mock_llm.complete = AsyncMock(return_value="A TypeScript component...")

    # Score always returns slightly better for variant
    call_count = 0

    async def mock_score_json(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        # Alternate: control gets 0.6, variant gets 0.65
        base = 0.65 if call_count % 2 == 0 else 0.6
        return {
            "patterns_followed": base,
            "correct_complete": base,
            "anti_patterns_avoided": base,
            "conventions_used": base,
        }

    mock_llm.complete_json = AsyncMock(
        side_effect=[
            # First call: variant generation
            {"content": "Use strict TypeScript", "insight_type": "convention", "confidence": 0.8},
            # Remaining calls: scoring (control + variant for each of 5 tasks = 10 calls)
            *[
                {
                    "patterns_followed": 0.6,
                    "correct_complete": 0.6,
                    "anti_patterns_avoided": 0.6,
                    "conventions_used": 0.6,
                }
            ]
            * 5,
            *[
                {
                    "patterns_followed": 0.7,
                    "correct_complete": 0.7,
                    "anti_patterns_avoided": 0.7,
                    "conventions_used": 0.7,
                }
            ]
            * 5,
        ]
    )

    findings = [
        {"snippet": "TypeScript strict mode improves safety", "url": "https://example.com", "title": "TS strict"}
    ]
    tasks = [
        {"description": f"Task {i}", "expected_quality_signals": ["uses TS"], "discipline": "tech"} for i in range(5)
    ]

    experiments = await run_experiment("architecture", "product:test", findings, tasks, mock_db, mock_llm)

    assert len(experiments) >= 1
    exp = experiments[0]
    assert "control_mean" in exp
    assert "variant_mean" in exp
    assert "improvement" in exp
    assert "p_value" in exp


@pytest.mark.asyncio
async def test_commit_logs_all_results():
    """Commit stage logs all experiments — winners AND losers."""
    from core.engine.sentinel.engines.domain_research import commit_results

    mock_db = AsyncMock()
    log_calls = []

    async def track_queries(query_str, params=None):
        if "CREATE experiment_log" in query_str:
            log_calls.append(params)
        return [[]]

    mock_db.query = track_queries

    experiments = [
        {
            "variant": {"content": "Winner insight", "insight_type": "fact", "confidence": 0.8},
            "finding": {"url": "https://ex.com", "snippet": "test"},
            "control_mean": 0.5,
            "variant_mean": 0.6,
            "improvement": 0.1,
            "p_value": 0.01,
            "significant": True,
            "synthetic_task_count": 20,
        },
        {
            "variant": {"content": "Loser insight", "insight_type": "fact", "confidence": 0.6},
            "finding": {"url": "", "snippet": ""},
            "control_mean": 0.5,
            "variant_mean": 0.48,
            "improvement": -0.02,
            "p_value": 0.3,
            "significant": False,
            "synthetic_task_count": 20,
        },
    ]

    result = await commit_results("architecture", "product:test", experiments, mock_db)

    assert result["winners"] == 1
    assert result["losers"] == 0  # not significant
    assert result["inconclusive"] == 1  # not significant
    assert len(log_calls) == 2  # Both logged


@pytest.mark.asyncio
async def test_specialty_based_grouping():
    """Research engine groups by specialty via specialties_loaded field."""
    from core.engine.sentinel.engines.domain_research import _get_eligible_specialties

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # First call: task counts
            [
                [
                    {"specialties_loaded": ["ml", "data"], "task_count": 15},
                    {"specialties_loaded": ["ml"], "task_count": 8},
                    {"specialties_loaded": ["frontend"], "task_count": 3},
                ]
            ],
            # Second call: specialty records
            [
                [
                    {"slug": "ml", "discipline_slug": "engineering", "id": "specialty:ml"},
                    {"slug": "data", "discipline_slug": "engineering", "id": "specialty:data"},
                ]
            ],
        ]
    )

    result = await _get_eligible_specialties("product:test", mock_db)

    assert "engineering" in result
    slugs = {s["slug"] for s in result["engineering"]}
    assert "ml" in slugs
    assert "data" in slugs


@pytest.mark.asyncio
async def test_no_budget_cap():
    """All eligible specialties are processed — no hardcoded cap."""
    from core.engine.sentinel.engines.domain_research import run_domain_research

    with (
        patch("core.engine.sentinel.engines.domain_research.pool") as mock_pool,
        patch(
            "core.engine.sentinel.engines.domain_research._get_eligible_specialties", new_callable=AsyncMock
        ) as mock_eligible,
        patch("core.engine.sentinel.engines.domain_research.research_domain", new_callable=AsyncMock) as mock_research,
    ):
        mock_conn = AsyncMock()
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        # 8 specialties across 2 disciplines — all should run
        mock_eligible.return_value = {
            "engineering": [{"slug": f"eng-{i}", "id": f"specialty:eng{i}"} for i in range(5)],
            "sciences": [{"slug": f"sci-{i}", "id": f"specialty:sci{i}"} for i in range(3)],
        }
        mock_research.return_value = []  # No findings = quick exit per specialty

        result = await run_domain_research("product:test")

        assert result["specialties_processed"] == 8
