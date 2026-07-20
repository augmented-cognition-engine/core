# tests/test_integration_overnight.py
"""Integration tests for overnight engines — DB required, LLM mocked.

Requires: SurrealDB running, schema applied.
"""

import pytest

pytestmark = pytest.mark.e2e
from unittest.mock import AsyncMock, patch


@pytest.fixture
async def test_org(db_pool):
    """Create a test org and return its ID."""
    product_id = "product:integration_test"
    async with db_pool.connection() as db:
        # Clean up any leftover test data
        await db.query("DELETE task WHERE product = product:integration_test")
        await db.query("DELETE insight WHERE product = product:integration_test")
        await db.query("DELETE research_queue WHERE product = product:integration_test")
        await db.query("DELETE product:integration_test")

        result = await db.query(
            """
            CREATE product:integration_test SET
                tenant = tenant:test,
                name = 'Integration Test Org'
            """
        )
        from core.engine.core.db import parse_rows

        rows = parse_rows(result)
        product_id = str(rows[0]["id"]) if rows else product_id
        yield product_id

        # Cleanup test data
        await db.query("DELETE task WHERE product = product:integration_test")
        await db.query("DELETE insight WHERE product = product:integration_test")
        await db.query("DELETE research_queue WHERE product = product:integration_test")
        await db.query("DELETE product:integration_test")


@pytest.fixture
async def cleanup_insights(db_pool):
    """Cleanup test insights after each test."""
    yield
    async with db_pool.connection() as db:
        await db.query("DELETE insight WHERE source_domain CONTAINS 'sentinel.'")
        await db.query("DELETE research_queue WHERE source IN ['failure-analysis', 'specialty-deepener']")


@pytest.mark.asyncio
async def test_failure_analysis_writes_correction(db_pool, test_org, cleanup_insights):
    """Create a rejected task, run failure analysis, verify correction insight."""
    async with db_pool.connection() as db:
        await db.query(
            """
            CREATE task SET
                product = <record>$product,
                product = <record>$product,
                description = 'Build a React 17 class component',
                domain_path = 'architecture',
                discipline = 'architecture',
                tags = ['architecture', 'best_practice'],
                output = 'Here is the class component with setState...',
                feedback_human = 'rejected',
                feedback_score = 0.2,
                self_assessment = 0.3,
                intelligence_loaded = {},
                completed_at = time::now()
            """,
            {"product": test_org},
        )

    llm_response = {
        "failure_type": "wrong_assumption",
        "root_cause": "Used class component pattern which is legacy in React 19",
        "correction": "React 19 uses function components with hooks as the primary pattern",
        "confidence": 0.9,
        "should_research": False,
    }

    with patch("core.engine.sentinel.engines.failure_analysis.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

        result = await run_failure_analysis(test_org)

    assert result["failures_analyzed"] >= 1
    assert result["corrections_written"] >= 1

    async with db_pool.connection() as db:
        insights = await db.query(
            """
            SELECT *
            FROM insight
            WHERE product = <record>$product
                AND source_domain = 'sentinel.failure-analysis'
                AND insight_type = 'correction'
            """,
            {"product": test_org},
        )

    rows = insights[0] if insights and isinstance(insights[0], list) else (insights or [])
    assert len(rows) >= 1
    correction = rows[0]
    assert correction["source_domain"] == "sentinel.failure-analysis"
    assert correction["insight_type"] == "correction"
    assert "auto-correction" in correction.get("tags", [])
    assert correction["status"] == "active"


@pytest.mark.asyncio
async def test_gap_researcher_consumes_queue(db_pool, test_org, cleanup_insights):
    """Create research_queue items, run gap researcher, verify consumed."""
    async with db_pool.connection() as db:
        await db.query(
            """
            CREATE research_queue SET
                product = <record>$product,
                product = <record>$product,
                query = 'Kubernetes HPA custom metrics adapter setup',
                context = 'Failure analysis: missing custom metrics knowledge',
                priority = 'high',
                source = 'failure-analysis',
                status = 'pending',
                created_at = time::now()
            """,
            {"product": test_org},
        )

    llm_findings = {
        "findings": [
            {
                "content": "K8s HPA supports custom metrics via metrics.k8s.io API",
                "insight_type": "fact",
                "confidence": 0.85,
                "tier": "specialty",
                "discipline": "devops",
            },
        ],
    }

    with patch("core.engine.sentinel.engines.gap_researcher.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=llm_findings)

        from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

        result = await run_gap_researcher(test_org)

    assert result["research_conducted"] >= 1
    assert result["insights_written"] >= 1
    assert result["queue_completed"] >= 1

    async with db_pool.connection() as db:
        rq = await db.query(
            """
            SELECT *
            FROM research_queue
            WHERE product = <record>$product AND source = 'failure-analysis'
            """,
            {"product": test_org},
        )

    rows = rq[0] if rq and isinstance(rq[0], list) else (rq or [])
    assert len(rows) >= 1
    assert rows[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_knowledge_verifier_confirms_insight(db_pool, test_org, cleanup_insights):
    """Create a stale insight, run verifier with 'confirmed' response."""
    from core.engine.core.db import parse_rows

    async with db_pool.connection() as db:
        create_result = await db.query(
            """
            CREATE insight SET
                product = <record>$product,
                product = <record>$product,
                content = 'Python supports pattern matching via match/case',
                insight_type = 'fact',
                tier = 'subdomain',
                source_domain = 'user',
                confidence = 0.6,
                tags = ['testing'],
                status = 'active',
                last_confirmed = time::now() - 100d,
                created_at = time::now() - 200d
            """,
            {"product": test_org},
        )
        created = parse_rows(create_result)
        assert len(created) >= 1, f"Failed to create insight: {create_result}"

    llm_response = {
        "outcome": "confirmed",
        "explanation": "Pattern matching is supported since Python 3.10",
    }

    with patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

        result = await run_knowledge_verifier(test_org)

    assert result["confirmed"] >= 1

    async with db_pool.connection() as db:
        insights = await db.query(
            """
            SELECT confidence
            FROM insight
            WHERE product = <record>$product
                AND content = 'Python supports pattern matching via match/case'
            """,
            {"product": test_org},
        )

    rows = insights[0] if insights and isinstance(insights[0], list) else (insights or [])
    assert len(rows) >= 1
    assert rows[0]["confidence"] > 0.6


@pytest.mark.asyncio
async def test_knowledge_verifier_updates_insight(db_pool, test_org, cleanup_insights):
    """Create stale insight, run verifier with 'updated', verify contradicted."""
    async with db_pool.connection() as db:
        await db.query(
            """
            CREATE insight SET
                product = <record>$product,
                product = <record>$product,
                content = 'React 17 is the latest version',
                insight_type = 'fact',
                tier = 'specialty',
                source_domain = 'user',
                confidence = 0.7,
                tags = ['ux', 'version'],
                status = 'active',
                last_confirmed = time::now() - 60d,
                created_at = time::now() - 200d
            """,
            {"product": test_org},
        )

    llm_response = {
        "outcome": "updated",
        "explanation": "React 19 is now the latest stable version",
        "updated_content": "React 19 is the latest stable version",
        "confidence": 0.95,
    }

    with patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=llm_response)

        from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

        result = await run_knowledge_verifier(test_org)

    assert result["updated"] >= 1

    async with db_pool.connection() as db:
        old = await db.query(
            """
            SELECT status, contradicted_by
            FROM insight
            WHERE product = <record>$product
                AND content = 'React 17 is the latest version'
            """,
            {"product": test_org},
        )

    rows = old[0] if old and isinstance(old[0], list) else (old or [])
    assert len(rows) >= 1
    assert rows[0]["status"] == "contradicted"
    assert rows[0].get("contradicted_by") is not None
