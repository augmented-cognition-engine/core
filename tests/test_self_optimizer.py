# tests/test_self_optimizer.py
"""Tests for self-optimizer sentinel engine."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.sentinel.engines.self_optimizer import (
    PatternEvidence,  # noqa: F401
    TaskEvidence,
    cluster_by_insight_overlap,
    detect_specialty_affinities,
    extract_task_evidence,  # noqa: F401
    run_self_optimizer,
)


def test_task_evidence_combined_score():
    ev = TaskEvidence(
        task_id="task:1",
        specialties_loaded=["llm-engineering"],
        insights_reflected=["insight:a", "insight:b"],
        utilization_rate=0.6,
        feedback_score=1.0,
        perspective="practitioner",
        engagement_perspectives=["practitioner"],
    )
    assert ev.task_combined_score == pytest.approx(0.6)


def test_cluster_by_insight_overlap_groups_similar():
    evidences = [
        TaskEvidence("t:1", ["s:a"], ["i:1", "i:2", "i:3"], 0.5, 1.0, "p", ["p"]),
        TaskEvidence("t:2", ["s:a"], ["i:1", "i:2", "i:4"], 0.6, 1.0, "p", ["p"]),
        TaskEvidence("t:3", ["s:b"], ["i:5", "i:6", "i:7"], 0.4, 0.5, "p", ["p"]),
    ]
    clusters = cluster_by_insight_overlap(evidences, min_jaccard=0.4)
    # t:1 and t:2 share i:1, i:2 (Jaccard = 2/4 = 0.5) → one cluster
    # t:3 shares nothing → separate or unclustered
    assert any(len(c) >= 2 for c in clusters)


def test_cluster_by_insight_overlap_no_overlap():
    evidences = [
        TaskEvidence("t:1", ["s:a"], ["i:1"], 0.5, 1.0, "p", ["p"]),
        TaskEvidence("t:2", ["s:a"], ["i:2"], 0.6, 1.0, "p", ["p"]),
    ]
    clusters = cluster_by_insight_overlap(evidences, min_jaccard=0.5)
    # No overlap → no clusters
    assert all(len(c) <= 1 for c in clusters)


def test_detect_specialty_affinities():
    evidences = [
        TaskEvidence("t:1", ["s:a", "s:b"], ["i:1"], 0.5, 1.0, "p", ["p"]),
        TaskEvidence("t:2", ["s:a", "s:b"], ["i:2"], 0.6, 1.0, "p", ["p"]),
        TaskEvidence("t:3", ["s:a", "s:b"], ["i:3"], 0.7, 1.0, "p", ["p"]),
    ]
    affinities = detect_specialty_affinities(evidences, min_tasks=3)
    assert len(affinities) >= 1
    pair = affinities[0]
    assert "s:a" in [pair["specialty_a"], pair["specialty_b"]]
    assert "s:b" in [pair["specialty_a"], pair["specialty_b"]]


def test_detect_specialty_affinities_below_threshold():
    evidences = [
        TaskEvidence("t:1", ["s:a", "s:b"], ["i:1"], 0.5, 1.0, "p", ["p"]),
    ]
    affinities = detect_specialty_affinities(evidences, min_tasks=3)
    assert len(affinities) == 0


@pytest.mark.asyncio
async def test_run_self_optimizer_returns_results():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # get state
            [{"threshold": 10, "min_tasks": 3, "min_combined_score": 0.25}],
            # get task evidence
            [],  # no qualifying tasks
            # update last_run
            [],
        ]
    )

    with (
        patch("core.engine.sentinel.engines.self_optimizer.pool") as mock_pool,
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_self_optimizer("product:default")

    assert "proposals" in result
    assert "affinities_created" in result


def test_engine_module_has_run_function():
    """Verify the engine module exposes the expected function."""
    from core.engine.sentinel.engines.self_optimizer import run_self_optimizer

    assert callable(run_self_optimizer)
    assert run_self_optimizer.__name__ == "run_self_optimizer"
