# tests/test_e2e_dual_graphs.py
"""End-to-end test for dual knowledge graph loading.

Requires: SurrealDB running, schema v025 applied, domains seeded (technology slug present).
"""

import pytest

from core.engine.core.db import parse_rows

pytestmark = pytest.mark.e2e

PREFIX = "DUAL-GRAPH-E2E"
ORG = "product:default"


# ---------------------------------------------------------------------------
# Cleanup fixture — autouse so it always runs regardless of test outcome
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def cleanup(db_pool):
    yield
    async with db_pool.connection() as db:
        await db.query(f"DELETE insight WHERE content CONTAINS '{PREFIX}'")
        await db.query("DELETE specialty WHERE slug = <string>$slug", {"slug": "dual-graph-test-spec"})


# ---------------------------------------------------------------------------
# test_dual_graph_loading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dual_graph_loading(db_pool, db_health):
    """Dual loader returns insights tagged with correct source_graph provenance.

    Steps:
    1. Create a specialty with insight_count=1 and min_threshold=1 so it passes the
       threshold check inside load_dual_intelligence.
    2. Attach a 'fact' insight to that specialty (specialty graph).
    3. Find the 'technology' domain and attach a 'convention' insight (org graph).
    4. Call load_dual_intelligence and assert the snapshot is well-formed.
    """
    from core.engine.orchestrator.dual_loader import load_dual_intelligence

    # ------------------------------------------------------------------
    # Step 1 — Create test specialty
    # ------------------------------------------------------------------
    async with db_pool.connection() as db:
        spec_result = await db.query(
            """
            CREATE specialty SET
                slug        = <string>$slug,
                name        = 'Dual Graph Test Specialty',
                product = <record>$product,
                parents     = [],
                perspective = 'practitioner',
                bootstrapped = true,
                insight_count = 3,
                min_threshold = 1
            """,
            {"slug": "dual-graph-test-spec", "product": ORG},
        )
    spec_rows = parse_rows(spec_result)
    assert spec_rows, "Failed to create test specialty"
    spec_id = str(spec_rows[0]["id"])

    # ------------------------------------------------------------------
    # Step 2 — Create specialty-graph insight
    # ------------------------------------------------------------------
    async with db_pool.connection() as db:
        ins_spec_result = await db.query(
            """
            CREATE insight SET
                product = <record>$product,
                specialty     = <record>$spec,
                insight_type  = 'fact',
                tier          = 'specialty',
                content       = <string>$content,
                status        = 'active',
                confidence    = 0.9,
                source_domain = 'sentinel.specialty',
                clearance     = 'open',
                created_at    = time::now(),
                updated_at    = time::now(),
                last_confirmed = time::now()
            """,
            {
                "product": ORG,
                "spec": spec_id,
                "content": f"{PREFIX}: use typed config objects over raw dicts",
            },
        )
    ins_spec_rows = parse_rows(ins_spec_result)
    assert ins_spec_rows, "Failed to create specialty insight"

    # ------------------------------------------------------------------
    # Step 3 — Create org-graph insight tagged with 'technology' domain
    # ------------------------------------------------------------------
    async with db_pool.connection() as db:
        ins_org_result = await db.query(
            """
            CREATE insight SET
                product = <record>$product,
                domain        = <string>$domain,
                insight_type  = 'convention',
                tier          = 'domain',
                content       = <string>$content,
                status        = 'active',
                confidence    = 0.8,
                source_domain = 'sentinel.org',
                clearance     = 'open',
                created_at    = time::now(),
                updated_at    = time::now(),
                last_confirmed = time::now()
            """,
            {
                "product": ORG,
                "domain": "technology",
                "content": f"{PREFIX}: prefer async generators for streaming responses",
            },
        )
    ins_org_rows = parse_rows(ins_org_result)
    assert ins_org_rows, "Failed to create org-graph insight"

    # ------------------------------------------------------------------
    # Step 4 — Call load_dual_intelligence
    # ------------------------------------------------------------------
    result = await load_dual_intelligence(
        specialties=["dual-graph-test-spec"],
        product_id=ORG,
        org_context=["technology"],
    )

    # ------------------------------------------------------------------
    # Step 5 — Assertions
    # ------------------------------------------------------------------
    # Top-level structure
    assert "total_count" in result
    assert "specialty_insights" in result
    assert "org_insights" in result
    assert "specialties_loaded" in result
    assert "insights" in result

    # At least one specialty insight was returned
    assert result["total_count"] >= 1, (
        f"Expected total_count >= 1, got {result['total_count']}. "
        f"specialty_insights={result['specialty_insights']}, gaps={result.get('gaps')}"
    )

    # Specialty insights carry the correct source_graph tag
    for item in result["specialty_insights"]:
        assert item["source_graph"] == "specialty", f"Specialty insight missing source_graph='specialty': {item}"

    # The test specialty slug appears in specialties_loaded
    assert "dual-graph-test-spec" in result["specialties_loaded"], (
        f"Expected 'dual-graph-test-spec' in specialties_loaded={result['specialties_loaded']}"
    )

    # Every insight in the merged list has a source_graph tag
    for item in result["insights"]:
        assert item.get("source_graph") in ("specialty", "org"), f"Merged insight has unexpected source_graph: {item}"
