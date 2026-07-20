from unittest.mock import MagicMock

import numpy as np
import pytest


def test_codesage_embedder_dimensions():
    from core.engine.embedding.codesage_embedder import CodeSageEmbedder

    assert CodeSageEmbedder().dimensions == 1024


def test_codesage_implements_protocol():
    from core.engine.embedding.base import Embedder
    from core.engine.embedding.codesage_embedder import CodeSageEmbedder

    assert isinstance(CodeSageEmbedder(), Embedder)


@pytest.mark.asyncio
async def test_codesage_embed_returns_correct_shape():
    from core.engine.embedding.codesage_embedder import CodeSageEmbedder

    embedder = CodeSageEmbedder()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.random.rand(2, 1024).astype(np.float32)
    embedder._model = mock_model
    result = await embedder.embed(["def foo(): pass", "class Bar: pass"])
    assert len(result) == 2
    assert len(result[0]) == 1024


@pytest.mark.asyncio
async def test_codesage_embed_empty_input():
    from core.engine.embedding.codesage_embedder import CodeSageEmbedder

    embedder = CodeSageEmbedder()
    result = await embedder.embed([])
    assert result == []


def test_get_embedder_returns_codesage():
    from unittest.mock import patch

    import core.engine.embedding.base

    with patch("core.engine.embedding.base.settings") as mock_settings:
        mock_settings.embedding_provider = "codesage"
        mock_settings.embedding_model = "CodeSage/CodeSage-Large-v2"
        mock_settings.ace_model_dir = "~/.ace/models"
        embedder = core.engine.embedding.base.get_embedder()
        from core.engine.embedding.codesage_embedder import CodeSageEmbedder

        assert isinstance(embedder, CodeSageEmbedder)
