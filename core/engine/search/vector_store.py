"""Qdrant vector store for semantic code search.

In-memory by default (dev, no external process needed).
Set QDRANT_URL env var to point at a Qdrant server for production.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_COLLECTION = "code_symbols"


class VectorStore:
    """Thin async wrapper around qdrant-client."""

    def __init__(self, dimensions: int = 1024, location: str = ":memory:") -> None:
        self._dimensions = dimensions
        self._location = os.environ.get("QDRANT_URL", location)
        self._client = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._client = QdrantClient(location=self._location)
        existing = {c.name for c in self._client.get_collections().collections}
        if _COLLECTION not in existing:
            self._client.create_collection(
                _COLLECTION,
                vectors_config=VectorParams(size=self._dimensions, distance=Distance.COSINE),
            )

    def _validate_vector(self, vector: list[float], operation: str) -> None:
        """Validate vector dimensions and content before sending to Qdrant."""
        if not vector:
            raise ValueError(f"VectorStore.{operation}: vector must not be empty")
        if len(vector) != self._dimensions:
            raise ValueError(
                f"VectorStore.{operation}: vector dimension mismatch (got {len(vector)}, expected {self._dimensions})"
            )

    async def upsert(self, id: str, vector: list[float], payload: dict) -> None:
        import asyncio

        if not id or not id.strip():
            raise ValueError("VectorStore.upsert: id must be a non-empty string")
        self._validate_vector(vector, "upsert")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_upsert, id, vector, payload)

    def _sync_upsert(self, id: str, vector: list[float], payload: dict) -> None:
        from qdrant_client.models import PointStruct

        self._ensure_client()
        point_id = abs(hash(id)) % (2**63)
        self._client.upsert(
            collection_name=_COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload={"id": id, **payload})],
        )
        logger.debug("Upserted vector id=%s dim=%d", id, len(vector))

    async def count_by_payload(self, key: str, values: list[str]) -> int:
        import asyncio

        self._validate_payload_selector(key, values, "count_by_payload")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_count_by_payload, key, values)

    def _sync_count_by_payload(self, key: str, values: list[str]) -> int:
        self._ensure_client()
        result = self._client.count(
            collection_name=_COLLECTION,
            count_filter=self._payload_filter(key, values),
            exact=True,
        )
        return int(result.count)

    async def delete_by_payload(self, key: str, values: list[str]) -> int:
        """Delete every point whose payload field `key` matches one of `values`.

        Deletion is payload-filter based by necessity: point ids are derived from
        a per-process salted hash (see _sync_upsert) and cannot be reconstructed
        by a later process. Returns the number of matching points removed,
        counted exactly before the delete.
        """
        import asyncio

        self._validate_payload_selector(key, values, "delete_by_payload")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_delete_by_payload, key, values)

    def _sync_delete_by_payload(self, key: str, values: list[str]) -> int:
        from qdrant_client.models import FilterSelector

        self._ensure_client()
        selector = self._payload_filter(key, values)
        matched = int(self._client.count(collection_name=_COLLECTION, count_filter=selector, exact=True).count)
        if matched:
            self._client.delete(
                collection_name=_COLLECTION,
                points_selector=FilterSelector(filter=selector),
                wait=True,
            )
        logger.debug("Deleted %d vectors where %s in %d values", matched, key, len(values))
        return matched

    @staticmethod
    def _validate_payload_selector(key: str, values: list[str], operation: str) -> None:
        if not key or not key.strip():
            raise ValueError(f"VectorStore.{operation}: key must be a non-empty string")
        if not values or any(not item or not item.strip() for item in values):
            raise ValueError(f"VectorStore.{operation}: values must be non-empty strings")

    @staticmethod
    def _payload_filter(key: str, values: list[str]):
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        return Filter(must=[FieldCondition(key=key, match=MatchAny(any=list(values)))])

    async def search(self, vector: list[float], limit: int = 10) -> list[dict]:
        import asyncio

        self._validate_vector(vector, "search")
        if limit < 1 or limit > 1000:
            raise ValueError(f"VectorStore.search: limit must be 1-1000, got {limit}")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_search, vector, limit)

    def _sync_search(self, vector: list[float], limit: int) -> list[dict]:
        self._ensure_client()
        try:
            response = self._client.query_points(
                collection_name=_COLLECTION,
                query=vector,
                limit=limit,
            )
            results = [{"score": r.score, **r.payload} for r in response.points]
            logger.debug("Vector search returned %d results (limit=%d)", len(results), limit)
            return results
        except Exception as exc:
            logger.warning("Qdrant search failed (returning empty results): %s", exc)
            return []


_store: VectorStore | None = None


def get_vector_store(dimensions: int = 1024) -> VectorStore:
    """Module-level VectorStore singleton.

    The singleton is initialized on first call with the given dimensions.
    Subsequent calls with a different dimension value are ignored — the
    original collection is returned with a warning logged.
    """
    global _store
    if _store is None:
        _store = VectorStore(dimensions=dimensions)
    elif _store._dimensions != dimensions:
        logger.warning(
            "get_vector_store() called with dimensions=%d but singleton has dimensions=%d — ignoring",
            dimensions,
            _store._dimensions,
        )
    return _store
