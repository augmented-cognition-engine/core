# tests/test_conflict_detector.py
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_check_contradiction_returns_true_for_contradicting():
    """Budget LLM identifies two contradicting statements."""
    from core.engine.sentinel.conflict_detector import check_contradiction

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "contradicts": True,
            "explanation": "Statement A says React 18, Statement B says React 19",
        }
    )

    result = await check_contradiction(
        content_a="React 18 is the latest stable version",
        content_b="React 19 is the latest stable version",
        llm=mock_llm,
    )
    assert result["contradicts"] is True
    assert "explanation" in result


@pytest.mark.asyncio
async def test_check_contradiction_returns_false_for_compatible():
    """Budget LLM identifies two compatible statements."""
    from core.engine.sentinel.conflict_detector import check_contradiction

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "contradicts": False,
            "explanation": "Both statements are about React but not contradictory",
        }
    )

    result = await check_contradiction(
        content_a="React uses a virtual DOM",
        content_b="React supports server-side rendering",
        llm=mock_llm,
    )
    assert result["contradicts"] is False


@pytest.mark.asyncio
async def test_check_new_insights_creates_conflict_records():
    """Post-synthesis hook: new insight contradicting existing creates conflict record."""
    from core.engine.sentinel.conflict_detector import check_new_insights

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # New insights
            [
                [
                    {
                        "id": "insight:new1",
                        "content": "React 19 is latest",
                        "subdomain": "subdomain:frontend",
                        "product": "product:test",
                    }
                ]
            ],
            # Existing insights in same subdomain (top 5 by confidence)
            [
                [
                    {
                        "id": "insight:old1",
                        "content": "React 18 is latest",
                        "confidence": 0.8,
                    }
                ]
            ],
            # Check for existing conflict between these two
            [[]],
            # CREATE conflict
            [{"id": "conflict:abc"}],
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "contradicts": True,
            "explanation": "Version conflict: 18 vs 19",
        }
    )

    result = await check_new_insights(
        new_insight_ids=["insight:new1"],
        product_id="product:test",
        db=mock_db,
        llm=mock_llm,
    )
    assert result["conflicts_found"] == 1
    assert result["pairs_checked"] == 1


@pytest.mark.asyncio
async def test_check_new_insights_skips_when_no_contradiction():
    """Post-synthesis hook: compatible insights do not create conflict records."""
    from core.engine.sentinel.conflict_detector import check_new_insights

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            [
                [
                    {
                        "id": "insight:new1",
                        "content": "React uses JSX",
                        "subdomain": "subdomain:frontend",
                        "product": "product:test",
                    }
                ]
            ],
            [[{"id": "insight:old1", "content": "React uses virtual DOM", "confidence": 0.8}]],
            # Check for existing conflict — none
            [[]],
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "contradicts": False,
            "explanation": "Compatible statements",
        }
    )

    result = await check_new_insights(
        new_insight_ids=["insight:new1"],
        product_id="product:test",
        db=mock_db,
        llm=mock_llm,
    )
    assert result["conflicts_found"] == 0
    assert result["pairs_checked"] == 1


@pytest.mark.asyncio
async def test_sweep_respects_max_comparisons_budget():
    """Daily sweep respects the 100-comparison budget."""
    from core.engine.sentinel.conflict_detector import sweep

    # Create 20 insights in a single subdomain — 20 choose 2 = 190 pairs
    # But budget is 100, so it should stop early
    insights = [
        {"id": f"insight:{i}", "content": f"Statement {i}", "subdomain": "subdomain:frontend", "confidence": 0.4}
        for i in range(20)
    ]

    # Build interleaved mock responses: for each pair, conflict check (empty) then CREATE
    pair_responses = []
    for j in range(100):
        pair_responses.append([[]])  # conflict check — no existing
        pair_responses.append([{"id": f"conflict:{j}"}])  # CREATE conflict

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # Query: low-confidence insights grouped by subdomain
            [insights],
            *pair_responses,
        ]
    )

    mock_llm = AsyncMock()
    mock_llm.complete_json = AsyncMock(
        return_value={
            "contradicts": True,
            "explanation": "Test contradiction",
        }
    )

    result = await sweep(
        product_id="product:test",
        db=mock_db,
        llm=mock_llm,
        max_comparisons=100,
    )

    assert result["pairs_checked"] <= 100


@pytest.mark.asyncio
async def test_sweep_skips_existing_conflicts():
    """Daily sweep skips pairs already in the conflict table."""
    from core.engine.sentinel.conflict_detector import sweep

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # Query: low-confidence insights
            [
                [
                    {"id": "insight:a", "content": "A", "subdomain": "subdomain:frontend", "confidence": 0.3},
                    {"id": "insight:b", "content": "B", "subdomain": "subdomain:frontend", "confidence": 0.4},
                ]
            ],
            # Check existing conflict between a and b — FOUND
            [[{"id": "conflict:existing"}]],
        ]
    )

    mock_llm = AsyncMock()
    # LLM should not be called since conflict already exists

    result = await sweep(
        product_id="product:test",
        db=mock_db,
        llm=mock_llm,
    )

    assert result["pairs_checked"] == 0
    assert result["pairs_skipped"] == 1
    mock_llm.complete_json.assert_not_called()
