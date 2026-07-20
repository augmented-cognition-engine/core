# tests/test_specialty_resolver.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_pool(return_value):
    """Create a mock pool that returns a fixed value from db.query()."""
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(return_value=return_value)
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_pool


# ---------------------------------------------------------------------------
# Static / pure-function tests
# ---------------------------------------------------------------------------


def test_perspectives_are_valid():
    from core.engine.orchestrator.specialty_resolver import PERSPECTIVES

    assert len(PERSPECTIVES) == 4
    assert PERSPECTIVES == {"theorist", "practitioner", "strategist", "operator"}


def test_find_similar_slug_exact_match():
    from core.engine.orchestrator.specialty_resolver import find_similar_slug

    result = find_similar_slug("ml-engineering", ["data-science", "ml-engineering", "backend"])
    assert result == "ml-engineering"


def test_find_similar_slug_close_match():
    """A slug that is visually similar but not identical should still match."""
    from core.engine.orchestrator.specialty_resolver import find_similar_slug

    # "machine-learning-engineering" is close enough to "ml-engineering" that
    # the implementation may or may not reach 0.7 — but a clearly similar pair
    # like "frontend-engineering" vs "frontend-engineer" always should.
    result = find_similar_slug(
        "frontend-engineer",
        ["backend-engineering", "frontend-engineering", "devops"],
    )
    assert result == "frontend-engineering"


def test_find_similar_slug_no_match():
    from core.engine.orchestrator.specialty_resolver import find_similar_slug

    result = find_similar_slug("quantum-cryptography", ["frontend", "backend", "devops"])
    assert result is None


# ---------------------------------------------------------------------------
# Async resolver tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_specialties_finds_existing():
    """When an exact slug exists in the DB the resolver puts it in resolved."""
    from core.engine.orchestrator.specialty_resolver import resolve_specialties

    existing_row = {
        "id": "specialty:abc",
        "slug": "ml-engineering",
        "name": "ML Engineering",
        "product": "org:acme",
        "perspective": "practitioner",
        "status": "active",
        "bootstrapped": False,
        "insight_count": 10,
        "min_threshold": 5,
    }

    with patch(
        "core.engine.orchestrator.specialty_resolver.pool",
        _mock_pool([existing_row]),
    ):
        result = await resolve_specialties(["ml-engineering"], "org:acme")

    assert len(result["resolved"]) == 1
    assert result["resolved"][0]["slug"] == "ml-engineering"
    assert result["gaps"] == []


@pytest.mark.asyncio
async def test_resolve_specialties_flags_below_threshold():
    """When insight_count < min_threshold the specialty lands in gaps as well."""
    from core.engine.orchestrator.specialty_resolver import resolve_specialties

    existing_row = {
        "id": "specialty:xyz",
        "slug": "rust-systems",
        "name": "Rust Systems",
        "product": "org:acme",
        "perspective": "practitioner",
        "status": "active",
        "bootstrapped": False,
        "insight_count": 2,
        "min_threshold": 10,
    }

    with patch(
        "core.engine.orchestrator.specialty_resolver.pool",
        _mock_pool([existing_row]),
    ):
        result = await resolve_specialties(["rust-systems"], "org:acme")

    assert len(result["resolved"]) == 1
    assert result["resolved"][0]["slug"] == "rust-systems"
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["slug"] == "rust-systems"
    assert result["gaps"][0]["reason"] == "below_threshold"
