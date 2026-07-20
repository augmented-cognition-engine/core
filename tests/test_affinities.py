# tests/test_affinities.py
"""Tests for specialty affinity CRUD and decay."""

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.intelligence.affinities import (
    compute_affinity_strength,
    decay_affinity,
    get_affinities_for_specialties,
)


def test_compute_affinity_strength():
    assert compute_affinity_strength(co_occurrence=10, avg_utilization=0.5, avg_feedback=0.8) > 0
    assert compute_affinity_strength(co_occurrence=10, avg_utilization=0.5, avg_feedback=0.8) <= 1.0


def test_compute_affinity_strength_zero_occurrence():
    assert compute_affinity_strength(co_occurrence=0, avg_utilization=0.5, avg_feedback=0.8) == 0.0


def test_compute_affinity_strength_increases_with_count():
    low = compute_affinity_strength(co_occurrence=3, avg_utilization=0.5, avg_feedback=0.8)
    high = compute_affinity_strength(co_occurrence=20, avg_utilization=0.5, avg_feedback=0.8)
    assert high > low


@pytest.mark.asyncio
async def test_get_affinities_returns_list():
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        return_value=[{"specialty_a": "specialty:a", "specialty_b": "specialty:b", "strength": 0.7}]
    )
    with patch("core.engine.intelligence.affinities.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await get_affinities_for_specialties(["specialty:a"], "product:default")
    assert len(result) >= 1


def test_decay_affinity_reduces_strength():
    current = 0.7
    new_strength = decay_affinity(current, below_baseline=True)
    assert new_strength < current


def test_decay_affinity_increases_above_baseline():
    current = 0.5
    new_strength = decay_affinity(current, below_baseline=False)
    assert new_strength > current


def test_decay_affinity_capped_at_1():
    assert decay_affinity(0.98, below_baseline=False) <= 1.0
