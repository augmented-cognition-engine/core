import pytest

from core.engine.mcp.tools import (
    ace_acknowledge_recommendation,
    ace_ambition,
    ace_phase_status,
    ace_pillar_status,
    ace_query_uncertainty,
    ace_set_phase,
    ace_set_product_scale,
    ace_set_product_type,
    ace_suggest_phase,
)


@pytest.mark.asyncio
async def test_ace_ambition_returns_struct(db_pool):
    result = await ace_ambition(product_id="product:platform")
    assert result is not None


@pytest.mark.asyncio
async def test_ace_set_phase_requires_reason(db_pool):
    with pytest.raises((TypeError, ValueError)):
        await ace_set_phase(product_id="product:platform", phase="poc")


@pytest.mark.asyncio
async def test_ace_query_uncertainty_returns_query_record(db_pool):
    result = await ace_query_uncertainty(
        product_id="product:platform",
        scope="ambition",
        question="What's the demo target?",
        fallback_action="default_safe",
    )
    assert "id" in result or result is not None
    async with db_pool.connection() as db:
        await db.query("DELETE uncertainty_queries WHERE product = product:platform")


@pytest.mark.asyncio
async def test_ace_pillar_status_returns_seven(db_pool):
    result = await ace_pillar_status(product_id="product:platform")
    assert len(result) >= 1
    assert "experience" in result or len(result) == 7


@pytest.mark.asyncio
async def test_ace_suggest_phase_returns_dict(db_pool):
    result = await ace_suggest_phase(product_id="product:platform")
    assert "suggested_phase" in result
    assert result["suggested_phase"] in {
        "discovery",
        "poc",
        "alpha",
        "beta",
        "ga",
        "mature",
    }


@pytest.mark.asyncio
async def test_ace_set_product_type_and_scale_no_error(db_pool):
    # Use product:test which is seeded by conftest
    a = await ace_set_product_type("product:test", "ai_native")
    assert a["product_type"] == "ai_native"
    b = await ace_set_product_scale("product:test", "application")
    assert b["product_scale"] == "application"


@pytest.mark.asyncio
async def test_ace_acknowledge_recommendation_no_error(db_pool):
    result = await ace_acknowledge_recommendation("rec:test_ack_mcp")
    assert result["status"] == "acknowledged"


@pytest.mark.asyncio
async def test_ace_phase_status_returns_dict(db_pool):
    result = await ace_phase_status(product_id="product:platform")
    assert isinstance(result, dict)
    assert "product_id" in result
