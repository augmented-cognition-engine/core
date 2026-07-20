"""No-op embedder — returns empty vectors. For air-gapped environments."""

from __future__ import annotations


class NoopEmbedder:
    @property
    def dimensions(self) -> int:
        return 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]
