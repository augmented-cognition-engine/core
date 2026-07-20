# tests/test_cross_pollination.py
"""Tests for cross-pollination of winning intelligence across sibling specialties."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_cross_pollinate_empty_winners():
    """Returns early with zero counts when no winners."""
    from core.engine.sentinel.engines.domain_research import cross_pollinate

    result = await cross_pollinate("engineering", [], "product:test", AsyncMock(), AsyncMock())
    assert result["attempted"] == 0
    assert result["winners"] == 0
    assert result["already_present"] == 0


def test_is_similar_match():
    """High similarity strings are detected as duplicates."""
    from core.engine.sentinel.engines.domain_research import _is_similar

    assert (
        _is_similar(
            "Use APCA for contrast checking in all UI",
            "Use APCA for contrast checking in all UI components",
        )
        is True
    )


def test_is_similar_no_match():
    """Low similarity strings are not duplicates."""
    from core.engine.sentinel.engines.domain_research import _is_similar

    assert _is_similar("Use APCA for contrast", "Deploy to Kubernetes") is False


@pytest.mark.asyncio
async def test_cross_pollinate_skips_duplicates():
    """Skips writing when similar insight already exists in sibling."""
    from core.engine.sentinel.engines.domain_research import cross_pollinate

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # Sibling query — returns one sibling
            [[{"slug": "data-eng", "id": "specialty:data-eng"}]],
            # Existing insights in sibling — contains similar content
            [[{"content": "New ML insight about transformers"}]],
        ]
    )

    winners = [
        {
            "specialty_slug": "ml",
            "variant": {
                "content": "New ML insight about transformers and attention",
                "insight_type": "fact",
                "confidence": 0.8,
            },
            "improvement": 0.05,
            "synthetic_tasks": [],
        }
    ]

    result = await cross_pollinate("engineering", winners, "product:test", mock_db, AsyncMock())
    assert result["already_present"] == 1
    assert result["attempted"] == 0


@pytest.mark.asyncio
async def test_cross_pollinate_runs_experiment():
    """Runs A/B test when no duplicate exists in sibling."""
    from core.engine.sentinel.engines.domain_research import cross_pollinate

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # Sibling query
            [[{"slug": "data-eng", "id": "specialty:data-eng"}]],
            # Existing insights — no match
            [[]],
            # experiment_log CREATE
            [[{"id": "experiment_log:1"}]],
        ]
    )

    mock_llm = AsyncMock()

    winners = [
        {
            "specialty_slug": "ml",
            "variant": {"content": "Completely novel insight", "insight_type": "fact", "confidence": 0.8},
            "improvement": 0.05,
            "synthetic_tasks": [{"description": "test task", "expected_quality_signals": []}],
        }
    ]

    with (
        patch("core.engine.sentinel.engines.domain_research.run_experiment", new_callable=AsyncMock) as mock_exp,
        patch("core.engine.sentinel.engines.domain_research.commit_results", new_callable=AsyncMock) as mock_commit,
    ):
        mock_exp.return_value = []
        mock_commit.return_value = {"winners": 0, "losers": 0, "inconclusive": 0}

        result = await cross_pollinate("engineering", winners, "product:test", mock_db, mock_llm)

    assert result["attempted"] == 1


@pytest.mark.asyncio
async def test_get_affinity_targets():
    """Finds cross-discipline specialties with strong affinities."""
    from core.engine.sentinel.engines.domain_research import _get_affinity_targets

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[
            [
                {
                    "slug_a": "ml",
                    "slug_b": "cognitive-science",
                    "strength": 0.75,
                },
                {
                    "slug_a": "ml",
                    "slug_b": "data-viz",
                    "strength": 0.3,
                },
            ]
        ]
    )

    targets = await _get_affinity_targets("ml", "product:test", mock_db)
    assert "cognitive-science" in targets
    assert "data-viz" not in targets


@pytest.mark.asyncio
async def test_get_affinity_targets_empty():
    """Returns empty list when no affinities exist."""
    from core.engine.sentinel.engines.domain_research import _get_affinity_targets

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[]])

    targets = await _get_affinity_targets("ml", "product:test", mock_db)
    assert targets == []
