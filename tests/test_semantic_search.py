import pytest


def test_cosine_similarity():
    from core.engine.search.semantic import cosine_similarity

    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(1.0)
    c = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, c) == pytest.approx(0.0)


def test_cosine_similarity_empty():
    from core.engine.search.semantic import cosine_similarity

    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], []) == 0.0


def test_cosine_similarity_batch():
    from core.engine.search.semantic import cosine_similarity_batch

    query = [1.0, 0.0, 0.0]
    candidates = [
        [1.0, 0.0, 0.0],
        [0.7, 0.7, 0.0],
        [0.0, 1.0, 0.0],
    ]
    scores = cosine_similarity_batch(query, candidates)
    assert len(scores) == 3
    assert scores[0] == pytest.approx(1.0, abs=0.01)
    assert scores[1] > 0.5
    assert scores[2] == pytest.approx(0.0, abs=0.01)


@pytest.mark.asyncio
async def test_semantic_search_ranks_by_similarity():
    from unittest.mock import AsyncMock, MagicMock, patch

    from core.engine.search.semantic import semantic_search

    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.query = AsyncMock(
        return_value=[
            {"id": "graph_file:a", "path": "auth.py", "embedding": [1.0, 0.0, 0.0]},
            {"id": "graph_file:b", "path": "db.py", "embedding": [0.0, 1.0, 0.0]},
            {"id": "graph_file:c", "path": "auth_utils.py", "embedding": [0.9, 0.1, 0.0]},
        ]
    )
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_embedder = AsyncMock()
    mock_embedder.embed = AsyncMock(return_value=[[0.95, 0.05, 0.0]])
    mock_embedder.dimensions = 3

    with (
        patch("core.engine.search.semantic.pool", mock_pool),
        patch("core.engine.search.semantic.get_embedder", return_value=mock_embedder),
    ):
        results = await semantic_search("authentication code", product_id="product:platform", limit=3)

    assert len(results) == 3
    paths = [r["path"] for r in results]
    assert paths.index("db.py") > paths.index("auth.py")


@pytest.mark.asyncio
async def test_semantic_search_noop_embedder_returns_empty():
    from unittest.mock import patch

    from core.engine.embedding.noop_embedder import NoopEmbedder
    from core.engine.search.semantic import semantic_search

    with patch("core.engine.search.semantic.get_embedder", return_value=NoopEmbedder()):
        results = await semantic_search("anything", product_id="product:platform")
    assert results == []
