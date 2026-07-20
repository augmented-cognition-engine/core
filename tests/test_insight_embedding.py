from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_embed_new_insights_stores_vectors():
    """embed_new_insights must call embedder and UPDATE insight with embedding."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(
        side_effect=[
            # SELECT insights without embeddings
            [[{"id": MagicMock(__str__=lambda s: "insight:abc"), "content": "use get_llm() not ClaudeProvider"}]],
            # UPDATE
            [[]],
        ]
    )

    class FakeConn:
        async def __aenter__(self):
            return mock_db

        async def __aexit__(self, *a):
            pass

    mock_embedder = AsyncMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * 768])

    with (
        patch("core.engine.worker.processor.pool") as mock_pool,
        patch("core.engine.worker.processor.get_embedder", return_value=mock_embedder),
    ):
        mock_pool.connection.return_value = FakeConn()
        from core.engine.worker.processor import embed_new_insights

        await embed_new_insights("product:platform")

    assert mock_embedder.embed.called, "embedder.embed must be called"
    update_calls = [c for c in mock_db.query.call_args_list if "UPDATE" in str(c)]
    assert update_calls, "Must UPDATE insight with embedding"


@pytest.mark.asyncio
async def test_embed_skips_when_noop_embedder():
    """embed_new_insights must skip entirely when embedder.dimensions == 0."""
    mock_embedder = MagicMock()
    mock_embedder.dimensions = 0

    with patch("core.engine.worker.processor.get_embedder", return_value=mock_embedder):
        from core.engine.worker.processor import embed_new_insights

        result = await embed_new_insights("product:platform")

    assert not mock_embedder.embed.called
    assert result == 0
