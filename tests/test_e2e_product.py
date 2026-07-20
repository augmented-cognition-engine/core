"""End-to-end product awareness tests. Requires SurrealDB with v032 schema."""

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


async def test_capability_lifecycle(db_pool):
    """Create capability, assess quality, check health, set vision."""
    from core.engine.product.map import ProductMap

    pm = ProductMap(db_pool)

    # Use a unique test org to avoid collisions
    test_org = "product:e2e_product_test"

    # Clean up any stale data from previous failed runs
    async with db_pool.connection() as db:
        await db.query("DELETE capability WHERE product = product:e2e_product_test")
        await db.query("DELETE capability_quality WHERE product = product:e2e_product_test")
        await db.query("DELETE product_vision WHERE product = product:e2e_product_test")

    try:
        # 1. Create a capability
        cap = await pm.upsert_capability(
            {
                "name": "Auth System",
                "slug": "auth",
                "description": "Authentication and authorization",
                "status": "built",
                "priority": "critical",
            },
            test_org,
        )
        assert cap is not None
        # The result should have a slug field
        assert cap.get("slug") == "auth" or cap.get("name") == "Auth System"

        # 2. Assess quality
        quality = await pm.update_quality(
            "auth",
            "security",
            {
                "score": 0.4,
                "gaps": ["no rate limiting", "no token refresh"],
                "evidence": ["checked engine/core/auth.py"],
                "assessed_by": "e2e_test",
            },
            test_org,
        )
        assert quality is not None

        # 3. Check health summary
        health = await pm.health_summary(test_org)
        assert "dimensions" in health
        assert health["total_capabilities"] >= 1
        if "security" in health["dimensions"]:
            assert health["dimensions"]["security"]["avg_score"] == 0.4

        # 4. Set product vision
        direction = await pm.set_vision(
            {
                "name": "AI PM for builder teams",
                "description": "Autonomous product management powered by systems thinking",
                "goals": [
                    {"goal": "Ship product awareness layer", "priority": "critical", "status": "in_progress"},
                    {"goal": "Security hardening", "priority": "high", "status": "planned"},
                ],
            },
            test_org,
        )
        assert direction is not None

        # 5. Verify vision is retrievable
        active = await pm.get_vision(test_org)
        assert active is not None
        assert active.get("active") is True

        # 6. Get capability with enrichment
        full_cap = await pm.get_capability("auth", test_org)
        if full_cap:
            assert "quality" in full_cap
            # Quality is a list of dimension assessments
            if full_cap["quality"]:
                dims = [q.get("dimension") for q in full_cap["quality"]]
                assert "security" in dims

    finally:
        # Cleanup all test data
        async with db_pool.connection() as db:
            await db.query("DELETE capability WHERE product = product:e2e_product_test")
            await db.query("DELETE capability_quality WHERE product = product:e2e_product_test")
            await db.query("DELETE product_vision WHERE product = product:e2e_product_test")
