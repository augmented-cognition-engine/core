# tests/test_phase2_integration.py
"""Phase 2 integration smoke tests — ranker+compressor pipeline + cache round-trip."""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _vec(angle_deg: float) -> list[float]:
    rad = math.radians(angle_deg)
    return [math.cos(rad), math.sin(rad)] + [0.0] * 766


# ---------------------------------------------------------------------------
# 1. Ranker + compressor pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ranker_compressor_pipeline_deduplicates():
    """rank_insights followed by compress_insights → near-dups become (+1 similar)."""
    insights = [
        {
            "id": "insight:1",
            "content": "Use type annotations everywhere",
            "confidence": 0.9,
            "source_graph": "specialty",
        },
        {
            "id": "insight:2",
            "content": "Add type hints to all functions",
            "confidence": 0.8,
            "source_graph": "specialty",
        },
        {
            "id": "insight:3",
            "content": "Completely different advice here",
            "confidence": 0.7,
            "source_graph": "specialty",
        },
    ]
    snapshot = {"insights": insights, "specialty_insights": [], "org_insights": []}

    # Inject _vec for near-dups (angles 0° and 1°) and distinct (90°)
    embedding_map = {
        "insight:1": _vec(0),
        "insight:2": _vec(1),
        "insight:3": _vec(90),
    }

    mock_embedder = MagicMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[_vec(0)])

    with (
        patch("core.engine.intelligence.ranker.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.ranker.pool") as mock_pool,
        patch("core.engine.intelligence.ranker.parse_rows") as mock_parse,
    ):
        # parse_rows: first call returns embeddings, second returns utilization (empty)
        mock_parse.side_effect = [
            [{"id": k, "embedding": v} for k, v in embedding_map.items()],
            [],
        ]
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(return_value=[])
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.ranker import rank_insights

        ranked = await rank_insights(snapshot, "write better python code", "product:test")

    from core.engine.intelligence.compressor import compress_insights

    compressed = compress_insights(ranked["insights"])

    assert len(compressed) == 2
    assert any("(+1 similar)" in i["content"] for i in compressed)


# ---------------------------------------------------------------------------
# 2. Cache store → lookup round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_store_lookup_roundtrip():
    """store() + lookup() returns the original result when vectors match."""
    vec = [1.0] + [0.0] * 767
    result_to_cache = {"discipline": "testing", "archetype": "creator", "mode": "reactive"}

    stored_entry: dict | None = None

    mock_embedder = MagicMock()
    mock_embedder.dimensions = 768
    mock_embedder.embed = AsyncMock(return_value=[vec])

    async def _fake_query(q, params=None):
        nonlocal stored_entry
        if "UPSERT" in q:
            stored_entry = {
                "id": "classification_cache:abc",
                "description_embedding": params.get("embedding", vec) if params else vec,
                "result": params.get("result", result_to_cache) if params else result_to_cache,
                "hit_count": 0,
            }
        return []

    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool,
    ):
        mock_db = AsyncMock()
        mock_db.query = AsyncMock(side_effect=_fake_query)
        mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import store

        await store("build a test suite", result_to_cache, "product:test")

    assert stored_entry is not None

    # Now simulate a lookup that returns the stored entry
    with (
        patch("core.engine.intelligence.classification_cache.get_embedder", return_value=mock_embedder),
        patch("core.engine.intelligence.classification_cache.pool") as mock_pool2,
        patch("core.engine.intelligence.classification_cache.parse_rows", return_value=[stored_entry]),
    ):
        mock_db2 = AsyncMock()
        mock_db2.query = AsyncMock(return_value=[])
        mock_pool2.connection.return_value.__aenter__ = AsyncMock(return_value=mock_db2)
        mock_pool2.connection.return_value.__aexit__ = AsyncMock(return_value=False)
        from core.engine.intelligence.classification_cache import lookup

        hit = await lookup("build a test suite", "product:test")

    assert hit == result_to_cache


# ---------------------------------------------------------------------------
# 3. All three modules importable
# ---------------------------------------------------------------------------


def test_all_phase2_modules_importable():
    """Sanity: all Phase 2 modules import without error."""
    from core.engine.intelligence import classification_cache, compressor, ranker  # noqa: F401

    assert callable(ranker.rank_insights)
    assert callable(compressor.compress_insights)
    assert callable(classification_cache.lookup)
    assert callable(classification_cache.store)
    assert callable(classification_cache.lookup_with_entry)
