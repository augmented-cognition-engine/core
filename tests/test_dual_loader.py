# tests/test_dual_loader.py
"""Tests for the dual-graph intelligence loader.

Mocks DB access so no live SurrealDB connection is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.orchestrator.dual_loader import _merge_snapshot, load_dual_intelligence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_insight(
    id: str, content: str, confidence: float, tier: str = "domain", insight_type: str = "pattern"
) -> dict:
    return {
        "id": id,
        "content": content,
        "confidence": confidence,
        "tier": tier,
        "insight_type": insight_type,
        "status": "active",
    }


# ---------------------------------------------------------------------------
# test_empty_specialties_returns_empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_specialties_returns_empty():
    """No specialties passed → specialty_insights is empty, no DB specialty query fired."""
    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        # DB should never be called for specialty queries when list is empty
        mock_pool.connection = AsyncMock()

        result = await load_dual_intelligence(
            specialties=[],
            product_id="product:test",
        )

    assert result["specialty_insights"] == []
    assert result["total_count"] >= 0  # backward compat key present


# ---------------------------------------------------------------------------
# test_specialty_insights_tagged_with_provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_specialty_insights_tagged_with_provenance():
    """Insights returned from the specialty graph get source_graph='specialty'."""
    raw_specialty_rows = [
        _make_insight("insight:s1", "Specialty tip one", 0.9),
        _make_insight("insight:s2", "Specialty tip two", 0.7),
    ]

    # Specialty slug resolution returns 2 specialty records above threshold
    specialty_records = [
        {"id": "specialty:eng", "slug": "eng", "insight_count": 10},
        {"id": "specialty:ml", "slug": "ml", "insight_count": 5},
    ]

    async def fake_query(sql, params=None):
        sql_stripped = sql.strip().lower()
        if "from specialty" in sql_stripped:
            return specialty_records
        if "from insight" in sql_stripped and "specialty in" in sql_stripped:
            return raw_specialty_rows
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_dual_intelligence(
            specialties=["eng", "ml"],
            product_id="product:test",
        )

    assert len(result["specialty_insights"]) == 2
    for item in result["specialty_insights"]:
        assert item["source_graph"] == "specialty"

    # The merged insights list must also carry the tag
    merged_ids = {i["id"] for i in result["insights"]}
    assert "insight:s1" in merged_ids
    assert "insight:s2" in merged_ids
    for item in result["insights"]:
        if item["id"] in ("insight:s1", "insight:s2"):
            assert item["source_graph"] == "specialty"


# ---------------------------------------------------------------------------
# test_org_insights_tagged_with_provenance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_org_insights_tagged_with_provenance():
    """Insights from the org graph get source_graph='org'."""
    raw_org_rows = [
        _make_insight("insight:o1", "Org insight one", 0.85),
    ]

    async def fake_query(sql, params=None):
        sql_stripped = sql.strip().lower()
        if "from specialty" in sql_stripped:
            return []
        if "from insight" in sql_stripped and "$product" in sql_stripped:
            return raw_org_rows
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_dual_intelligence(
            specialties=[],
            product_id="product:test",
            org_context=["engineering"],
        )

    assert len(result["org_insights"]) == 1
    assert result["org_insights"][0]["source_graph"] == "org"

    # Appears in merged list too
    assert any(i["source_graph"] == "org" for i in result["insights"])


# ---------------------------------------------------------------------------
# test_gaps_reported_for_below_threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gaps_reported_for_below_threshold():
    """Specialties whose insight_count < min_threshold are reported in gaps."""
    # "sparse" specialty has only 1 insight — below default threshold of 3
    specialty_records = [
        {"id": "specialty:sparse", "slug": "sparse", "insight_count": 1},
    ]
    raw_specialty_rows = [
        _make_insight("insight:sp1", "Sparse insight", 0.5),
    ]

    async def fake_query(sql, params=None):
        sql_stripped = sql.strip().lower()
        if "from specialty" in sql_stripped:
            return specialty_records
        if "from insight" in sql_stripped:
            return raw_specialty_rows
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    with patch("core.engine.orchestrator.dual_loader.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_dual_intelligence(
            specialties=["sparse"],
            product_id="product:test",
        )

    assert "gaps" in result
    assert "sparse" in result["gaps"]


# ---------------------------------------------------------------------------
# test_merge_snapshot_structure
# ---------------------------------------------------------------------------


def test_merge_snapshot_structure():
    """_merge_snapshot returns a dict with all required keys."""
    specialty_insights = [
        {
            "id": "insight:a",
            "content": "A",
            "confidence": 0.9,
            "tier": "domain",
            "insight_type": "pattern",
            "source_graph": "specialty",
        },
    ]
    org_insights = [
        {
            "id": "insight:b",
            "content": "B",
            "confidence": 0.8,
            "tier": "org",
            "insight_type": "rule",
            "source_graph": "org",
        },
    ]

    snapshot = _merge_snapshot(
        specialty_insights=specialty_insights,
        org_insights=org_insights,
        specialties_loaded=["eng"],
        org_context_loaded=["engineering"],
        gaps=["ml"],
    )

    # Backward compat keys
    assert "insights" in snapshot
    assert "total_count" in snapshot
    assert "recent_signals" in snapshot
    assert "raw_context" in snapshot

    # Dual-graph specific keys
    assert "specialty_insights" in snapshot
    assert "org_insights" in snapshot
    assert "specialties_loaded" in snapshot
    assert "org_context_loaded" in snapshot
    assert "gaps" in snapshot

    # Content checks
    assert snapshot["total_count"] == 2
    assert len(snapshot["insights"]) == 2
    ids = {i["id"] for i in snapshot["insights"]}
    assert ids == {"insight:a", "insight:b"}

    # Each insight in the merged list has all required fields
    required_fields = {"id", "content", "confidence", "tier", "insight_type", "source_graph"}
    for item in snapshot["insights"]:
        assert required_fields <= set(item.keys()), f"Missing fields in {item}"


# ---------------------------------------------------------------------------
# test_merge_snapshot_includes_failure_memory_and_decisions
# ---------------------------------------------------------------------------


def test_merge_snapshot_includes_failure_memory_and_decisions_keys():
    """_merge_snapshot always includes failure_memory and decisions keys (backward compat)."""
    snapshot = _merge_snapshot(
        specialty_insights=[],
        org_insights=[],
        specialties_loaded=[],
        org_context_loaded=[],
        gaps=[],
    )
    assert "failure_memory" in snapshot
    assert "decisions" in snapshot
    assert snapshot["failure_memory"] == []
    assert snapshot["decisions"] == []


# ---------------------------------------------------------------------------
# test_load_dual_intelligence_discipline_triggers_failure_memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_dual_intelligence_with_discipline_calls_failure_memory():
    """When discipline is provided, _load_failure_memory is called with discipline + product_id."""
    from unittest.mock import AsyncMock

    with (
        patch(
            "core.engine.orchestrator.loader._load_failure_memory",
            new=AsyncMock(return_value=[{"type": "failure", "content": "DB timeout pattern"}]),
        ) as mock_fm,
        patch(
            "core.engine.orchestrator.loader._load_recent_decisions",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await load_dual_intelligence(
            specialties=[],
            product_id="product:test",
            discipline="architecture",
        )

    mock_fm.assert_awaited_once_with("architecture", "product:test")
    assert result["failure_memory"] == [{"type": "failure", "content": "DB timeout pattern"}]


@pytest.mark.asyncio
async def test_load_dual_intelligence_without_discipline_skips_failure_memory():
    """When discipline is empty (default), _load_failure_memory is NOT called."""
    from unittest.mock import AsyncMock

    with (
        patch(
            "core.engine.orchestrator.loader._load_failure_memory",
            new=AsyncMock(return_value=[]),
        ) as mock_fm,
        patch(
            "core.engine.orchestrator.loader._load_recent_decisions",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await load_dual_intelligence(
            specialties=[],
            product_id="product:test",
            # discipline omitted → defaults to ""
        )

    mock_fm.assert_not_awaited()
    assert result["failure_memory"] == []


@pytest.mark.asyncio
async def test_load_dual_intelligence_always_loads_decisions():
    """decisions are always loaded regardless of whether discipline is provided."""
    from unittest.mock import AsyncMock

    decisions = [{"title": "Use SurrealDB RecordID for org comparisons"}]
    with (
        patch(
            "core.engine.orchestrator.loader._load_failure_memory",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "core.engine.orchestrator.loader._load_recent_decisions",
            new=AsyncMock(return_value=decisions),
        ) as mock_dec,
    ):
        result = await load_dual_intelligence(
            specialties=[],
            product_id="product:test",
        )

    mock_dec.assert_awaited_once_with("product:test", discipline="")
    assert result["decisions"] == decisions


@pytest.mark.asyncio
async def test_load_dual_intelligence_failure_memory_exception_is_non_fatal():
    """If _load_failure_memory raises, the call still succeeds with empty failure_memory."""
    from unittest.mock import AsyncMock

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("DB unreachable")

    with (
        patch("core.engine.orchestrator.loader._load_failure_memory", new=AsyncMock(side_effect=_boom)),
        patch(
            "core.engine.orchestrator.loader._load_recent_decisions",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await load_dual_intelligence(
            specialties=[],
            product_id="product:test",
            discipline="security",
        )

    assert result["failure_memory"] == []
    assert result["decisions"] == []
