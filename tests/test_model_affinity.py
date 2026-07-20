# tests/test_model_affinity.py
"""Tests for per-model insight affinity tracking.

Extension to insight_utilization: also track per-model_class load/attribution.
Over time this reveals which insights work best for which model classes
(Haiku needs concrete examples, Sonnet needs patterns, Opus needs framing).

The loader can then slice intelligence by target model's learned affinity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_normalize_model_class_claude_families():
    from core.engine.intelligence.model_affinity import normalize_model_class

    assert normalize_model_class("claude-opus-4-7") == "opus"
    assert normalize_model_class("claude-opus-4-7-20260402") == "opus"
    assert normalize_model_class("claude-sonnet-4-6") == "sonnet"
    assert normalize_model_class("claude-haiku-4-5-20251001") == "haiku"


def test_normalize_model_class_non_claude():
    from core.engine.intelligence.model_affinity import normalize_model_class

    # Non-Claude fallback to a normalized vendor prefix
    assert normalize_model_class("gpt-4o") == "gpt"
    assert normalize_model_class("gemini-2.5-pro") == "gemini"


def test_normalize_model_class_empty_returns_unknown():
    from core.engine.intelligence.model_affinity import normalize_model_class

    assert normalize_model_class("") == "unknown"
    assert normalize_model_class(None) == "unknown"


@pytest.mark.asyncio
async def test_update_affinity_upserts_per_model_class():
    from core.engine.intelligence.model_affinity import update_model_affinity

    captured: list[tuple[str, dict]] = []

    async def fake_query(sql, params=None):
        captured.append((sql, params or {}))
        return [[{"loaded_count": 1, "attributed_count": 0}]]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    await update_model_affinity(
        product_id="product:test",
        loaded_ids=["insight:a", "insight:b"],
        attributed_ids=["insight:a"],
        model_class="sonnet",
        db=mock_db,
    )

    assert len(captured) == 2
    # All records must carry the model_class tag
    for _sql, params in captured:
        assert params.get("model_class") == "sonnet"


@pytest.mark.asyncio
async def test_update_affinity_noop_on_empty_loaded():
    from core.engine.intelligence.model_affinity import update_model_affinity

    mock_db = AsyncMock()
    mock_db.query = AsyncMock()

    await update_model_affinity(
        product_id="product:test",
        loaded_ids=[],
        attributed_ids=[],
        model_class="opus",
        db=mock_db,
    )
    mock_db.query.assert_not_called()


@pytest.mark.asyncio
async def test_update_affinity_non_fatal_on_db_error():
    from core.engine.intelligence.model_affinity import update_model_affinity

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=RuntimeError("boom"))

    # Must not raise
    await update_model_affinity(
        product_id="product:test",
        loaded_ids=["insight:a"],
        attributed_ids=[],
        model_class="haiku",
        db=mock_db,
    )


@pytest.mark.asyncio
async def test_get_model_affinity_returns_ordered_scores():
    """The loader uses this to bias re-ranking by model-class."""
    from core.engine.intelligence.model_affinity import get_model_affinity

    async def fake_query(sql, params=None):
        return [
            [
                {"insight": "insight:a", "affinity_score": 0.8},
                {"insight": "insight:b", "affinity_score": 0.2},
            ]
        ]

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=fake_query)

    mapping = await get_model_affinity(mock_db, product_id="product:test", model_class="opus")
    assert mapping == {"insight:a": 0.8, "insight:b": 0.2}
