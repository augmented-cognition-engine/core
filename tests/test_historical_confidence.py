"""Tests for historical confidence enrichment."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_db(monkeypatch):
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    from core.engine.core import db as db_module

    monkeypatch.setattr(db_module, "pool", mock_pool)
    return mock_conn


@pytest.mark.asyncio
async def test_enrich_with_history(mock_db):
    mock_db.query.return_value = [
        {"perspective": "practitioner", "feedback_human": "accepted", "self_assessment": 0.85, "util_rate": 0.7},
        {"perspective": "practitioner", "feedback_human": "accepted", "self_assessment": 0.9, "util_rate": 0.8},
        {"perspective": "strategist", "feedback_human": "edited", "self_assessment": 0.75, "util_rate": 0.6},
    ]
    from core.engine.orchestrator.history import enrich_classification

    result = await enrich_classification({"domain_path": "architecture", "archetype": "creator"}, "product:default")
    ctx = result["historical_context"]
    assert ctx["similar_task_count"] == 3
    assert ctx["avg_feedback"] > 0.8
    assert "Strong track record" in ctx["confidence_note"]


@pytest.mark.asyncio
async def test_enrich_empty_history(mock_db):
    mock_db.query.return_value = []
    from core.engine.orchestrator.history import enrich_classification

    result = await enrich_classification({"domain_path": "observability", "archetype": "creator"}, "product:default")
    ctx = result["historical_context"]
    assert ctx["similar_task_count"] == 0
    assert "First task" in ctx["confidence_note"]


@pytest.mark.asyncio
async def test_enrich_missing_domain():
    from core.engine.orchestrator.history import enrich_classification

    result = await enrich_classification({"archetype": "creator"}, "product:default")
    assert result["historical_context"]["similar_task_count"] == 0


def test_generate_note_thresholds():
    from core.engine.orchestrator.history import _generate_note

    assert "Strong" in _generate_note(5, 0.85)
    assert "Moderate" in _generate_note(5, 0.65)
    assert "Challenging" in _generate_note(5, 0.4)
    assert "Limited" in _generate_note(2, 0.9)
    assert "First task" in _generate_note(0, 0.0)
