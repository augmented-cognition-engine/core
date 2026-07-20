"""Semantic search — cosine similarity over code embeddings."""

from __future__ import annotations

import logging
import math

from core.engine.core.db import parse_rows, pool
from core.engine.embedding.base import get_embedder

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


def cosine_similarity_batch(query: list[float], candidates: list[list[float]]) -> list[float]:
    """Compute cosine similarity between query and each candidate."""
    if not query or not candidates:
        return []
    try:
        import numpy as np

        q = np.array(query, dtype=np.float32)
        c = np.array(candidates, dtype=np.float32)
        q_norm = q / max(np.linalg.norm(q), 1e-9)
        c_norms = np.linalg.norm(c, axis=1, keepdims=True)
        c_norms = np.clip(c_norms, 1e-9, None)
        c_normalized = c / c_norms
        scores = c_normalized @ q_norm
        return scores.tolist()
    except ImportError:
        return [cosine_similarity(query, c) for c in candidates]


async def semantic_search(
    query: str,
    product_id: str,
    limit: int = 20,
    search_functions: bool = False,
) -> list[dict]:
    """Search code by semantic similarity."""
    embedder = get_embedder()
    if embedder.dimensions == 0:
        return []

    query_vectors = await embedder.embed([query])
    if not query_vectors or not query_vectors[0]:
        return []
    query_vec = query_vectors[0]

    table = "graph_function" if search_functions else "graph_file"
    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                f"SELECT id, path, name, embedding FROM {table} WHERE embedding != NONE ORDER BY path",
            )
        )

    if not rows:
        return []

    candidates = []
    embeddings = []
    for row in rows:
        emb = row.get("embedding")
        if emb and len(emb) == embedder.dimensions:
            candidates.append(row)
            embeddings.append(emb)

    if not embeddings:
        return []

    scores = cosine_similarity_batch(query_vec, embeddings)

    results = []
    for i, score in enumerate(scores):
        results.append(
            {
                "id": str(candidates[i].get("id", "")),
                "path": candidates[i].get("path", candidates[i].get("name", "")),
                "score": round(score, 4),
                "type": "function" if search_functions else "file",
            }
        )

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]
