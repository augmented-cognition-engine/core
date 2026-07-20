# tests/test_dual_loader_affinities.py
"""Tests for affinity-based supplementary loading in the dual loader.

Verifies that when gaps exist (below-threshold specialties), the loader
queries specialty_affinity and loads linked specialty insights.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.dual_loader import load_dual_intelligence

# ---------------------------------------------------------------------------
# test_affinity_query_made_when_gaps_exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_affinity_query_made_when_gaps_exist():
    """When gaps exist, get_affinities_for_specialties is called and linked
    specialty insights are appended to specialty_insights."""

    # "sparse" has insight_count=1 → below threshold → becomes a gap
    # "linked" is a different specialty linked via affinity to "sparse"
    specialty_records = [
        {"id": "specialty:sparse", "slug": "sparse", "insight_count": 1},
    ]

    sparse_affinity = {
        "specialty_a": "specialty:sparse",
        "specialty_b": "specialty:linked",
        "strength": 0.7,
        "product": "product:test",
    }

    supplementary_insight = {
        "id": "insight:supp1",
        "content": "Supplementary from linked specialty",
        "confidence": 0.75,
        "tier": "domain",
        "insight_type": "pattern",
        "status": "active",
    }

    async def fake_query(sql, params=None):
        sql_stripped = sql.strip().lower()
        # Step 0: specialty slug resolution query
        if "from specialty" in sql_stripped:
            return specialty_records
        # Step 1 / Step 1b: insight queries (supplementary load)
        if "from insight" in sql_stripped:
            return [supplementary_insight]
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    mock_affinities = AsyncMock(return_value=[sparse_affinity])

    with (
        patch("core.engine.orchestrator.dual_loader.pool") as mock_pool,
        patch(
            "core.engine.intelligence.affinities.get_affinities_for_specialties",
            mock_affinities,
        ),
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_dual_intelligence(
            specialties=["sparse"],
            product_id="product:test",
        )

    # The gap was detected
    assert "sparse" in result["gaps"]

    # The affinity function was called once (with gap IDs and product_id)
    mock_affinities.assert_awaited_once()
    call_args = mock_affinities.call_args
    # First positional arg is the list of gap specialty IDs
    gap_ids_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("specialty_ids", [])
    assert any("sparse" in str(gid) for gid in gap_ids_arg)

    # Supplementary insight is present in specialty_insights
    supp_ids = {i["id"] for i in result["specialty_insights"]}
    assert "insight:supp1" in supp_ids

    # And in the merged list
    merged_ids = {i["id"] for i in result["insights"]}
    assert "insight:supp1" in merged_ids
