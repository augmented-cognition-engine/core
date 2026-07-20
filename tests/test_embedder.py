import pytest


def test_noop_embedder_returns_empty_vectors():
    from core.engine.embedding.noop_embedder import NoopEmbedder

    embedder = NoopEmbedder()
    assert embedder.dimensions == 0


@pytest.mark.asyncio
async def test_noop_embed_returns_empty_lists():
    from core.engine.embedding.noop_embedder import NoopEmbedder

    embedder = NoopEmbedder()
    result = await embedder.embed(["hello world", "def foo(): pass"])
    assert len(result) == 2
    assert result[0] == []
    assert result[1] == []


def test_get_embedder_returns_noop_for_none_provider():
    from unittest.mock import patch

    import core.engine.embedding.base

    with patch("core.engine.embedding.base.settings") as mock_settings:
        mock_settings.embedding_provider = "none"
        embedder = core.engine.embedding.base.get_embedder()
        assert embedder.dimensions == 0


def test_noop_implements_protocol():
    from core.engine.embedding.base import Embedder
    from core.engine.embedding.noop_embedder import NoopEmbedder

    assert isinstance(NoopEmbedder(), Embedder)


@pytest.mark.allow_network  # integration test: downloads the ONNX model (off-box) — see test docstring
@pytest.mark.asyncio
async def test_onnx_embedder_produces_vectors():
    """Integration test — requires onnxruntime + model download."""
    pytest.importorskip("onnxruntime")
    from core.engine.embedding.onnx_embedder import OnnxEmbedder

    embedder = OnnxEmbedder(model_name="CodeRankEmbed", model_dir="/tmp/ace-test-models")
    assert embedder.dimensions == 768

    results = await embedder.embed(["def hello(): return 'world'"])
    assert len(results) == 1
    assert len(results[0]) == 768
    import math

    magnitude = math.sqrt(sum(x * x for x in results[0]))
    assert 0.99 < magnitude < 1.01


@pytest.mark.allow_network  # integration test: downloads the ONNX model (off-box) — see test docstring
@pytest.mark.asyncio
async def test_onnx_embedder_batch():
    """Batch embedding returns correct count."""
    pytest.importorskip("onnxruntime")
    from core.engine.embedding.onnx_embedder import OnnxEmbedder

    embedder = OnnxEmbedder(model_name="CodeRankEmbed", model_dir="/tmp/ace-test-models")
    results = await embedder.embed(
        [
            "def foo(): pass",
            "class Bar: pass",
            "import os",
        ]
    )
    assert len(results) == 3
    assert all(len(v) == 768 for v in results)


@pytest.mark.allow_network  # integration test: downloads the ONNX model (off-box) — see test docstring
@pytest.mark.asyncio
async def test_onnx_embedder_similar_code_has_higher_similarity():
    """Similar code should have higher cosine similarity than unrelated code."""
    pytest.importorskip("onnxruntime")
    from core.engine.embedding.onnx_embedder import OnnxEmbedder

    embedder = OnnxEmbedder(model_name="CodeRankEmbed", model_dir="/tmp/ace-test-models")
    results = await embedder.embed(
        [
            "def authenticate_user(username, password): return verify(username, password)",
            "def verify_credentials(user, pwd): return check_password(user, pwd)",
            "def calculate_fibonacci(n): return fib(n-1) + fib(n-2)",
        ]
    )

    # Cosine similarity
    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(x * x for x in b) ** 0.5
        return dot / (na * nb)

    auth_vs_verify = cosine(results[0], results[1])
    auth_vs_fib = cosine(results[0], results[2])

    # Auth functions should be more similar to each other than to fibonacci
    assert auth_vs_verify > auth_vs_fib


@pytest.mark.asyncio
async def test_embed_functions_returns_int():
    from unittest.mock import AsyncMock, MagicMock, patch

    with (
        patch("core.engine.scanner.embed_hook.get_embedder") as mock_get_emb,
        patch("core.engine.scanner.embed_hook.pool") as mock_pool,
        patch("core.engine.scanner.embed_hook.parse_rows") as mock_parse,
    ):
        mock_emb = MagicMock()
        mock_emb.dimensions = 1024
        mock_emb.embed = AsyncMock(return_value=[])
        mock_get_emb.return_value = mock_emb

        mock_parse.return_value = []  # no unembedded functions → returns 0

        mock_db = MagicMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(),
            )
        )

        from core.engine.scanner.embed_hook import embed_functions

        count = await embed_functions("/tmp")
        assert count == 0  # no rows → 0 embeddings, no crash
