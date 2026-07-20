# tests/test_e2e_overnight.py
"""End-to-end test: simulate a full overnight cycle.

Creates realistic data, runs all engines in order, verifies the system
is "smarter" afterward.

Requires: SurrealDB running, schema applied.
LLM: mocked for deterministic results.
"""

import pytest

pytestmark = pytest.mark.e2e
from unittest.mock import AsyncMock, patch

from core.engine.core.db import parse_one, parse_rows


@pytest.fixture
async def e2e_org(db_pool):
    """Create an org with realistic test data for overnight simulation."""
    async with db_pool.connection() as db:
        product_id = "product:e2e_overnight"
        # Cleanup leftover data from previous failed runs
        await db.query("DELETE research_queue WHERE product = product:e2e_overnight")
        await db.query("DELETE insight WHERE product = product:e2e_overnight")
        for i in range(3):
            await db.query(f"DELETE task:e2e_on_fail_{i}")
        for slug in ["react", "kubernetes"]:
            await db.query(f"DELETE specialty:e2e_on_{slug}")
        for i in range(10):
            await db.query(f"DELETE insight:e2e_on_stale_{i}")
        await db.query("DELETE product:e2e_overnight")

        await db.query(
            """
            CREATE product:e2e_overnight SET
                tenant = tenant:test,
                name = 'E2E Overnight Org',
                slug = 'e2e-overnight'
            """
        )

        # 3 rejected tasks
        for i, (desc, discipline) in enumerate(
            [
                ("Build React class component", "ux"),
                ("Configure K8s HPA custom metrics", "devops"),
                ("Design REST API without versioning", "api_design"),
            ]
        ):
            task_result = await db.query(
                f"""
                CREATE task:e2e_on_fail_{i} SET
                    product = <record>$product,
                    description = '{desc}',
                    domain_path = '{discipline}',
                    discipline = '{discipline}',
                    output = 'Incorrect output for task {i}',
                    feedback_human = 'rejected',
                    feedback_score = 0.2,
                    self_assessment = 0.3,
                    intelligence_loaded = {{}},
                    completed_at = time::now()
                """,
                {"product": product_id},
            )
            if isinstance(task_result, str) or not parse_rows(task_result):
                raise AssertionError(f"Failed to create task:e2e_on_fail_{i}: {task_result}")

        # 10 stale insights
        stale_insights = [
            ("React 17 is the latest", "version", 0.7),
            ("Node 16 is LTS", "version", 0.6),
            ("Company uses Jenkins CI", "process", 0.5),
            ("AWS us-east-1 is cheapest", "pricing", 0.4),
            ("Team lead is Alice", "personnel", 0.5),
            ("GDPR requires consent forms", "regulation", 0.8),
            ("Python 3.10 is latest", "version", 0.6),
            ("REST is better than GraphQL", "fact", 0.3),
            ("Docker Compose v2 syntax", "fact", 0.5),
            ("Terraform 1.3 features", "version", 0.4),
        ]
        for i, (content, category, conf) in enumerate(stale_insights):
            await db.query(
                f"""
                CREATE insight:e2e_on_stale_{i} SET
                    product = <record>$product,
                    content = '{content}',
                    insight_type = 'fact',
                    tier = 'subdomain',
                    source_domain = 'user',
                    confidence = {conf},
                    tags = ['architecture', '{category}'],
                    status = 'active',
                    last_confirmed = time::now() - 120d,
                    created_at = time::now() - 200d
                """,
                {"product": product_id},
            )

        # 2 thin specialties
        for name, slug, tc in [("React", "react", 20), ("Kubernetes", "kubernetes", 15)]:
            await db.query(
                f"""
                CREATE specialty:e2e_on_{slug} SET
                    product = <record>$product,
                    name = '{name}',
                    slug = '{slug}',
                    task_count = {tc},
                    subdomain = subdomain:frontend
                """,
                {"product": product_id},
            )

        yield product_id

        # Cleanup
        await db.query("DELETE product:e2e_overnight")
        for i in range(3):
            await db.query(f"DELETE task:e2e_on_fail_{i}")
        for slug in ["react", "kubernetes"]:
            await db.query(f"DELETE specialty:e2e_on_{slug}")
        for i in range(10):
            await db.query(f"DELETE insight:e2e_on_stale_{i}")
        await db.query("DELETE insight WHERE source_domain = 'sentinel.failure-analysis'")
        await db.query("DELETE insight WHERE source_domain = 'sentinel.gap-researcher'")
        await db.query("DELETE research_queue WHERE product = product:e2e_overnight")


@pytest.mark.asyncio
async def test_full_overnight_cycle(db_pool, e2e_org):
    """Simulate a full overnight run: all 4 engines in sequence."""

    failure_response = {
        "failure_type": "knowledge_gap",
        "root_cause": "Missing knowledge",
        "correction": "Corrected knowledge for this failure",
        "confidence": 0.85,
        "should_research": True,
        "research_query": "Research query for knowledge gap",
    }

    research_findings = {
        "findings": [
            {
                "content": "Research finding from gap researcher",
                "insight_type": "fact",
                "confidence": 0.8,
                "tier": "subdomain",
                "discipline": "architecture",
            },
        ],
    }

    verify_confirmed = {"outcome": "confirmed", "explanation": "Still valid"}
    verify_updated = {
        "outcome": "updated",
        "explanation": "Outdated info",
        "updated_content": "Updated knowledge",
        "confidence": 0.95,
    }
    verify_cannot = {
        "outcome": "cannot_verify",
        "explanation": "Cannot verify without external data",
    }

    deepener_topics = {
        "topics": [
            {"query": "Topic 1 for deepening", "context": "Missing core knowledge"},
            {"query": "Topic 2 for deepening", "context": "Missing patterns"},
            {"query": "Topic 3 for deepening", "context": "Missing practices"},
        ],
    }

    # Verify test data was created
    async with db_pool.connection() as db:
        task_check = await db.query(
            "SELECT id, feedback_human FROM task WHERE product = <record>$product",
            {"product": e2e_org},
        )
        task_rows = parse_rows(task_check)
        assert len(task_rows) >= 3, f"Expected 3 tasks, got {len(task_rows)}: {task_check}"

    # Engine 1: Failure Analysis (3:00 AM)
    with patch("core.engine.sentinel.engines.failure_analysis.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=failure_response)
        from core.engine.sentinel.engines.failure_analysis import run_failure_analysis

        fa_result = await run_failure_analysis(e2e_org, budget=5)

    assert fa_result["failures_analyzed"] == 3
    assert fa_result["corrections_written"] == 3
    assert fa_result["research_queued"] == 3

    # Engine 2: Gap Researcher (3:30 AM)
    with patch("core.engine.sentinel.engines.gap_researcher.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=research_findings)
        from core.engine.sentinel.engines.gap_researcher import run_gap_researcher

        gr_result = await run_gap_researcher(e2e_org, budget=10)

    assert gr_result["research_conducted"] >= 3
    assert gr_result["insights_written"] >= 3
    assert gr_result["queue_completed"] >= 3

    # Engine 3: Knowledge Verifier (4:00 AM)
    verify_responses = [verify_confirmed, verify_updated, verify_cannot] * 4

    with patch("core.engine.sentinel.engines.knowledge_verifier.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(side_effect=verify_responses)
        from core.engine.sentinel.engines.knowledge_verifier import run_knowledge_verifier

        kv_result = await run_knowledge_verifier(e2e_org, budget=10)

    assert kv_result["candidates"] >= 10
    assert kv_result["confirmed"] >= 1
    assert kv_result["updated"] >= 1
    assert kv_result["cannot_verify"] >= 1

    # Engine 4: Specialty Deepener (4:30 AM)
    with patch("core.engine.sentinel.engines.specialty_deepener.llm") as mock_llm:
        mock_llm.complete_json = AsyncMock(return_value=deepener_topics)
        from core.engine.sentinel.engines.specialty_deepener import run_specialty_deepener

        sd_result = await run_specialty_deepener(e2e_org, budget=5)

    assert sd_result["thin_specialties_found"] >= 1
    assert sd_result["research_queued"] >= 3

    # Final verification
    async with db_pool.connection() as db:
        corrections = await db.query(
            """
            SELECT count() AS n
            FROM insight
            WHERE product = <record>$product AND source_domain = 'sentinel.failure-analysis'
            GROUP ALL
            """,
            {"product": e2e_org},
        )
        corr_row = parse_one(corrections)
        corr_count = corr_row["n"] if corr_row else 0
        assert corr_count >= 3, f"Expected 3+ corrections, got {corr_count}"

        gap_insights = await db.query(
            """
            SELECT count() AS n
            FROM insight
            WHERE product = <record>$product AND source_domain = 'sentinel.gap-researcher'
            GROUP ALL
            """,
            {"product": e2e_org},
        )
        gap_row = parse_one(gap_insights)
        gap_count = gap_row["n"] if gap_row else 0
        assert gap_count >= 3, f"Expected 3+ gap-researcher insights, got {gap_count}"

        contradicted = await db.query(
            """
            SELECT count() AS n
            FROM insight
            WHERE product = <record>$product AND status = 'contradicted'
            GROUP ALL
            """,
            {"product": e2e_org},
        )
        cont_row = parse_one(contradicted)
        cont_count = cont_row["n"] if cont_row else 0
        assert cont_count >= 1, f"Expected 1+ contradicted insight, got {cont_count}"

        research = await db.query(
            """
            SELECT count() AS n
            FROM research_queue
            WHERE product = <record>$product AND source = 'specialty-deepener'
            GROUP ALL
            """,
            {"product": e2e_org},
        )
        rq_row = parse_one(research)
        rq_count = rq_row["n"] if rq_row else 0
        assert rq_count >= 3, f"Expected 3+ deepener research items, got {rq_count}"
