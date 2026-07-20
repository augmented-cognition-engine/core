# tests/test_injection.py
"""Tests for proactive perspective injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_classification(perspectives: list[str], complexity: str = "simple") -> dict:
    """Build a minimal classification dict for injection tests."""
    return {
        "domain_path": "architecture",
        "archetype": "executor",
        "mode": "reactive",
        "complexity": complexity,
        "perspective": perspectives[0] if perspectives else "practitioner",
        "specialties": [],
        "org_context": [],
        "engagement": {
            "perspectives": list(perspectives),
            "adversarial_pair": None,
            "rationale": "",
        },
    }


def _mock_pool_multi(query_map: dict):
    """Mock pool whose conn.query dispatches by SQL substring.

    query_map: {substring: return_value}
    """
    mock_pool = MagicMock()
    mock_conn = AsyncMock()

    async def _query(sql, params=None):
        sql_lower = sql.strip().lower()
        for key, value in query_map.items():
            if key.lower() in sql_lower:
                return value
        return []

    mock_conn.query = _query
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


# ---------------------------------------------------------------------------
# test_no_injection_when_all_perspectives_recent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_injection_when_all_perspectives_recent():
    """All perspectives used recently → no injections added."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    classification = _make_classification(["theorist", "practitioner", "strategist", "operator"])

    # All 4 perspectives appear in recent task results
    recent_task_rows = [
        {"perspective": "theorist", "cnt": 3},
        {"perspective": "practitioner", "cnt": 5},
        {"perspective": "strategist", "cnt": 2},
        {"perspective": "operator", "cnt": 1},
    ]
    # Specialties exist for each perspective
    specialty_rows = [
        {"perspective": "theorist"},
        {"perspective": "practitioner"},
        {"perspective": "strategist"},
        {"perspective": "operator"},
    ]

    mock_pool = _mock_pool_multi(
        {
            "task": recent_task_rows,
            "specialty": specialty_rows,
            "milestone": [],
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    # All 4 were already present — no injections
    assert result["engagement"]["perspectives"] == ["theorist", "practitioner", "strategist", "operator"]
    assert result["engagement"].get("injected", []) == []


# ---------------------------------------------------------------------------
# test_complexity_escalation_adds_perspective
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complexity_escalation_adds_perspective():
    """complex complexity + single practitioner → theorist injected."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    classification = _make_classification(["practitioner"], complexity="complex")

    mock_pool = _mock_pool_multi(
        {
            "task": [],
            "specialty": [],
            "milestone": [],
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    perspectives = result["engagement"]["perspectives"]
    assert "practitioner" in perspectives
    assert "theorist" in perspectives

    injected = result["engagement"].get("injected", [])
    assert len(injected) == 1
    assert injected[0]["perspective"] == "theorist"
    assert injected[0]["injected"] is True
    assert "complexity" in injected[0]["reason"].lower()


# ---------------------------------------------------------------------------
# test_injection_preserves_existing_perspectives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_injection_preserves_existing_perspectives():
    """Injected perspectives are added, not a replacement — existing ones stay."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    # strategist only, complex → practitioner should be injected (from escalation map)
    classification = _make_classification(["strategist"], complexity="complex")

    mock_pool = _mock_pool_multi(
        {
            "task": [],
            "specialty": [],
            "milestone": [],
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    perspectives = result["engagement"]["perspectives"]
    # Original strategist must still be present
    assert "strategist" in perspectives
    # Complementary practitioner injected
    assert "practitioner" in perspectives


# ---------------------------------------------------------------------------
# test_milestone_proximity_injects_operator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_milestone_proximity_injects_operator():
    """Milestone due within 7 days and no operator → operator injected."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    classification = _make_classification(["theorist", "practitioner"])

    milestone_rows = [{"id": "milestone:m1", "title": "Launch", "due": "2026-03-28"}]

    mock_pool = _mock_pool_multi(
        {
            "task": [
                {"perspective": "theorist", "cnt": 2},
                {"perspective": "practitioner", "cnt": 4},
            ],
            "specialty": [],
            "milestone": milestone_rows,
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    perspectives = result["engagement"]["perspectives"]
    assert "operator" in perspectives

    injected = result["engagement"].get("injected", [])
    operator_injections = [i for i in injected if i["perspective"] == "operator"]
    assert len(operator_injections) == 1
    assert operator_injections[0]["injected"] is True


# ---------------------------------------------------------------------------
# test_recency_gap_injects_perspective
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recency_gap_injects_perspective():
    """Perspective has specialties but hasn't been used in 7 days → inject it."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    # Only practitioner currently, strategist has specialties but no recent tasks
    classification = _make_classification(["practitioner"])

    # Tasks only show practitioner recently
    recent_task_rows = [{"perspective": "practitioner", "cnt": 3}]
    # But strategist has a specialty for this org
    specialty_rows = [
        {"perspective": "practitioner"},
        {"perspective": "strategist"},
    ]

    mock_pool = _mock_pool_multi(
        {
            "task": recent_task_rows,
            "specialty": specialty_rows,
            "milestone": [],
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    perspectives = result["engagement"]["perspectives"]
    assert "strategist" in perspectives

    injected = result["engagement"].get("injected", [])
    strat_injections = [i for i in injected if i["perspective"] == "strategist"]
    assert len(strat_injections) == 1
    assert "recency" in strat_injections[0]["reason"].lower()


# ---------------------------------------------------------------------------
# test_cap_at_four_perspectives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cap_at_four_perspectives():
    """Total perspectives never exceed 4 even if multiple injections would fire."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    # 3 perspectives, complex → escalation would add a 4th, but we're already near the cap
    classification = _make_classification(["practitioner", "strategist", "operator"], complexity="complex")

    mock_pool = _mock_pool_multi(
        {
            "task": [],
            "specialty": [],
            "milestone": [{"id": "milestone:x", "title": "Deadline"}],
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    assert len(result["engagement"]["perspectives"]) <= 4


# ---------------------------------------------------------------------------
# test_db_failure_does_not_block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_failure_does_not_block():
    """If DB queries fail, injection skips gracefully and classification is returned."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    classification = _make_classification(["practitioner"], complexity="complex")

    # Pool that raises on every query
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(side_effect=RuntimeError("DB down"))
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    # Still returns a valid classification dict
    assert "engagement" in result
    assert "perspectives" in result["engagement"]


# ---------------------------------------------------------------------------
# test_no_duplicate_injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_duplicate_injection():
    """Perspective already in list is never added twice."""
    from core.engine.orchestrator.injection import inject_missing_perspectives

    # theorist + practitioner already present; complexity=complex with practitioner
    # would normally escalate to theorist, but theorist is already there
    classification = _make_classification(["practitioner", "theorist"], complexity="complex")

    mock_pool = _mock_pool_multi(
        {
            "task": [],
            "specialty": [],
            "milestone": [],
        }
    )

    with patch("core.engine.orchestrator.injection.pool", mock_pool):
        result = await inject_missing_perspectives(classification, "product:default")

    perspectives = result["engagement"]["perspectives"]
    # theorist must not appear twice
    assert perspectives.count("theorist") == 1
