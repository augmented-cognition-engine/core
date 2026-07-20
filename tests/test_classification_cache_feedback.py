from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_lookup_with_entry_returns_tuple_on_hit():
    from core.engine.intelligence.classification_cache import lookup_with_entry

    mock_candidate = {
        "id": "classification_cache:abc123",
        "description_embedding": [0.1, 0.2],
        "result": {"discipline": "api_design", "mode": "reactive"},
        "hit_count": 3,
    }

    mock_embedder = MagicMock()
    mock_embedder.dimensions = 2
    mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2]])

    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[mock_candidate]),
        patch("core.engine.intelligence.classification_cache.cosine_similarity_batch", return_value=[0.95]),
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await lookup_with_entry("build a REST API", "product:test")

    assert result is not None
    classification, entry_id = result
    assert classification == {"discipline": "api_design", "mode": "reactive"}
    assert "classification_cache:abc123" in entry_id


@pytest.mark.asyncio
async def test_lookup_backward_compat():
    from core.engine.intelligence.classification_cache import lookup

    mock_candidate = {
        "id": "classification_cache:xyz",
        "description_embedding": [0.1],
        "result": {"discipline": "testing"},
        "hit_count": 1,
    }

    mock_embedder = MagicMock()
    mock_embedder.dimensions = 1
    mock_embedder.embed = AsyncMock(return_value=[[0.1]])

    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[mock_candidate]),
        patch("core.engine.intelligence.classification_cache.cosine_similarity_batch", return_value=[0.95]),
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await lookup("run tests", "product:test")

    assert isinstance(result, dict)
    assert result == {"discipline": "testing"}


@pytest.mark.asyncio
async def test_on_zero_utilization_hit_increments_counter():
    from core.engine.intelligence.classification_cache import on_zero_utilization_hit

    queries_issued = []

    async def mock_query(q, *args, **kwargs):
        queries_issued.append(q)
        if "SELECT" in q:
            return [{"consecutive_zero_utilization": 1}]
        return []

    mock_db = AsyncMock()
    mock_db.query = mock_query

    with (
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", side_effect=lambda x: x),
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await on_zero_utilization_hit("classification_cache:abc")

    assert any("consecutive_zero_utilization" in q for q in queries_issued)
    assert not any("DELETE" in q for q in queries_issued)


@pytest.mark.asyncio
async def test_on_zero_utilization_hit_invalidates_at_3():
    from core.engine.intelligence.classification_cache import on_zero_utilization_hit

    queries_issued = []

    async def mock_query(q, *args, **kwargs):
        queries_issued.append(q)
        if "SELECT" in q:
            return [{"consecutive_zero_utilization": 3}]
        return []

    mock_db = AsyncMock()
    mock_db.query = mock_query

    with (
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
        patch("core.engine.intelligence.classification_cache.parse_rows", side_effect=lambda x: x),
    ):
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await on_zero_utilization_hit("classification_cache:stale")

    assert any("DELETE" in q for q in queries_issued)


@pytest.mark.asyncio
async def test_on_utilization_hit_resets_counter():
    from core.engine.intelligence.classification_cache import on_utilization_hit

    queries_issued = []

    async def mock_query(q, *args, **kwargs):
        queries_issued.append(q)
        return []

    mock_db = AsyncMock()
    mock_db.query = mock_query

    with patch("core.engine.intelligence.classification_cache.pool") as mock_pool:
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

        await on_utilization_hit("classification_cache:good")

    assert any("consecutive_zero_utilization = 0" in q for q in queries_issued)
