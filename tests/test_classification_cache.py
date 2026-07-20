# tests/test_classification_cache.py
"""Tests for engine.intelligence.classification_cache."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_embedder(dims: int = 768) -> MagicMock:
    embedder = MagicMock()
    embedder.dimensions = dims
    embedder.embed = AsyncMock(return_value=[[0.5] * dims])
    return embedder


@pytest.mark.asyncio
async def test_lookup_miss_on_empty_db():
    """Returns None when no entries exist for the product."""
    mock_embedder = _make_embedder()
    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[]),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import lookup

        result = await lookup("fix the auth bug", "product:test")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_hit_above_threshold():
    """Returns cached result when cosine similarity meets LOW_THRESHOLD."""

    vec = [1.0] + [0.0] * 767  # unit vector
    cached_entry = {
        "id": "classification_cache:abc123",
        "description": "fix the auth bug",
        "description_embedding": vec,
        "result": {"discipline": "security", "archetype": "fixer"},
        "hit_count": 0,
    }
    mock_embedder = _make_embedder()
    mock_embedder.embed = AsyncMock(return_value=[vec])  # same vector → sim=1.0
    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[cached_entry]),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[cached_entry])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import lookup

        result = await lookup("fix the auth bug", "product:test")
    assert result == {"discipline": "security", "archetype": "fixer"}


@pytest.mark.asyncio
async def test_lookup_miss_below_threshold():
    """Returns None when cosine similarity is below LOW_THRESHOLD."""

    vec_a = [1.0] + [0.0] * 767  # unit vector along axis 0
    vec_b = [0.0, 1.0] + [0.0] * 766  # unit vector along axis 1 — orthogonal, sim=0
    cached_entry = {
        "id": "classification_cache:abc123",
        "description": "completely different task",
        "description_embedding": vec_b,
        "result": {"discipline": "security"},
        "hit_count": 0,
    }
    mock_embedder = _make_embedder()
    mock_embedder.embed = AsyncMock(return_value=[vec_a])
    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[cached_entry]),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[cached_entry])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import lookup

        result = await lookup("totally new feature request", "product:test")
    assert result is None


@pytest.mark.asyncio
async def test_store_calls_upsert():
    """store() calls DB query with UPSERT."""
    mock_embedder = _make_embedder()
    captured_queries = []

    async def _capture_query(q, params=None):
        captured_queries.append(q)
        return []

    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(side_effect=_capture_query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import store

        await store("fix auth bug", {"discipline": "security"}, "product:test")

    assert any("UPSERT" in q or "upsert" in q.lower() for q in captured_queries)


@pytest.mark.asyncio
async def test_noop_on_disabled_embedder():
    """lookup() returns None immediately when embedder.dimensions == 0."""
    mock_embedder = _make_embedder(dims=0)
    with patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder):
        from core.engine.intelligence.classification_cache import lookup

        result = await lookup("any task", "product:test")
    assert result is None


@pytest.mark.asyncio
async def test_hit_increments_hit_count():
    """On a cache hit, the hit_count update query is called."""
    vec = [1.0] + [0.0] * 767
    cached_entry = {
        "id": "classification_cache:abc123",
        "description": "fix the auth bug",
        "description_embedding": vec,
        "result": {"discipline": "security"},
        "hit_count": 2,
    }
    mock_embedder = _make_embedder()
    mock_embedder.embed = AsyncMock(return_value=[vec])
    update_called = []

    async def _capture_query(q, params=None):
        if "hit_count" in q:
            update_called.append(q)
        return []

    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[cached_entry]),
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(side_effect=_capture_query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import lookup

        result = await lookup("fix the auth bug", "product:test")
    assert result == {"discipline": "security"}
    assert len(update_called) > 0
