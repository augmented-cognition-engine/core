"""Embedder protocol and factory — mirrors get_llm() pattern."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.engine.core.config import settings


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        ...

    @property
    def dimensions(self) -> int:
        """Vector dimensionality."""
        ...


def get_embedder() -> Embedder:
    """Return configured embedder based on settings.embedding_provider."""
    provider = settings.embedding_provider

    if provider == "none":
        from core.engine.embedding.noop_embedder import NoopEmbedder

        return NoopEmbedder()

    if provider == "onnx":
        from core.engine.embedding.onnx_embedder import OnnxEmbedder

        return OnnxEmbedder(
            model_name=settings.embedding_model,
            model_dir=settings.ace_model_dir,
        )

    if provider == "codesage":
        from core.engine.embedding.codesage_embedder import CodeSageEmbedder

        return CodeSageEmbedder(
            model_name=settings.embedding_model,
            model_dir=settings.ace_model_dir,
        )

    # Fallback to noop
    from core.engine.embedding.noop_embedder import NoopEmbedder

    return NoopEmbedder()
