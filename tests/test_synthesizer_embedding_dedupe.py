# tests/test_synthesizer_embedding_dedupe.py
"""Tests for embedding-based dedupe before LLM synthesis.

When an observation is cosine-similar (>= 0.85) to an existing insight, skip the
LLM call for that observation and instead boost the matched insight's confidence.
Reduces LLM call volume ~30-40% by short-circuiting obvious duplicates.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from core.engine.capture.synthesizer import Synthesizer


class _FakeEmbedder:
    dimensions = 3

    def __init__(self, vectors: dict[str, list[float]]):
        self._vectors = vectors

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors.get(t, [0.0, 0.0, 0.0]) for t in texts]


def _mk_synth(db_pool=None) -> Synthesizer:
    s = Synthesizer(product_id="product:test", workspace_id=None, batch_size=99)
    s._db_pool = db_pool
    return s


def test_cosine_similarity_is_available():
    """Synthesizer must expose a cosine similarity helper."""
    from core.engine.capture.synthesizer import _cosine_similarity

    assert _cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)
    assert _cosine_similarity([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_similarity_handles_zero_vector():
    """Zero vector input must not raise ZeroDivisionError."""
    from core.engine.capture.synthesizer import _cosine_similarity

    assert _cosine_similarity([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 0.0


@pytest.mark.asyncio
async def test_dedupe_skips_near_duplicate_observations():
    """If an observation's embedding matches an existing insight above threshold, skip LLM."""
    existing = [
        {
            "id": "insight:dup_target",
            "content": "existing insight about auth",
            "embedding": [1.0, 0.0, 0.0],
            "confidence": 0.7,
        }
    ]
    observations = [
        {"id": "obs:1", "content": "duplicate observation about auth", "confidence": 0.7},
        {"id": "obs:2", "content": "genuinely new observation", "confidence": 0.7},
    ]
    embeddings = {
        "duplicate observation about auth": [1.0, 0.0, 0.0],  # cosine 1.0 with existing
        "genuinely new observation": [0.0, 1.0, 0.0],  # cosine 0.0 with existing
    }

    synth = _mk_synth()
    with patch("core.engine.capture.synthesizer.get_embedder", return_value=_FakeEmbedder(embeddings)):
        # Mock the boost call so we can assert it
        synth._boost_insight_confidence = AsyncMock()
        non_matched, auto_merged = await synth._embedding_dedupe(observations, existing)

    assert len(non_matched) == 1
    assert non_matched[0]["id"] == "obs:2"
    assert auto_merged == [("obs:1", "insight:dup_target")]
    synth._boost_insight_confidence.assert_awaited_once_with("insight:dup_target")


@pytest.mark.asyncio
async def test_dedupe_keeps_observations_below_threshold():
    """Observations with cosine < 0.85 must pass through to the LLM unchanged."""
    existing = [
        {"id": "insight:x", "content": "x", "embedding": [1.0, 0.0, 0.0], "confidence": 0.7},
    ]
    observations = [
        {"id": "obs:1", "content": "somewhat related observation", "confidence": 0.7},
    ]
    embeddings = {
        "somewhat related observation": [0.8, 0.6, 0.0],  # cosine = 0.8 with existing (below 0.85)
    }

    synth = _mk_synth()
    synth._boost_insight_confidence = AsyncMock()
    with patch("core.engine.capture.synthesizer.get_embedder", return_value=_FakeEmbedder(embeddings)):
        non_matched, auto_merged = await synth._embedding_dedupe(observations, existing)

    assert len(non_matched) == 1
    assert auto_merged == []
    synth._boost_insight_confidence.assert_not_called()


@pytest.mark.asyncio
async def test_dedupe_skips_when_no_existing_embeddings():
    """If no existing insight has an embedding, all observations pass through."""
    existing = [
        {"id": "insight:x", "content": "x", "confidence": 0.7},  # no embedding
    ]
    observations = [{"id": "obs:1", "content": "anything", "confidence": 0.7}]
    embeddings = {"anything": [1.0, 0.0, 0.0]}

    synth = _mk_synth()
    with patch("core.engine.capture.synthesizer.get_embedder", return_value=_FakeEmbedder(embeddings)):
        non_matched, auto_merged = await synth._embedding_dedupe(observations, existing)

    assert len(non_matched) == 1
    assert auto_merged == []


@pytest.mark.asyncio
async def test_dedupe_noop_when_embedder_dimensions_zero():
    """Noop embedder → dedupe must be a no-op, all observations pass through."""
    existing = [{"id": "insight:x", "content": "x", "embedding": [0.0, 0.0, 0.0]}]
    observations = [{"id": "obs:1", "content": "anything"}]

    class _Noop:
        dimensions = 0

        async def embed(self, texts):
            return [[] for _ in texts]

    synth = _mk_synth()
    with patch("core.engine.capture.synthesizer.get_embedder", return_value=_Noop()):
        non_matched, auto_merged = await synth._embedding_dedupe(observations, existing)

    assert len(non_matched) == len(observations)
    assert auto_merged == []


@pytest.mark.asyncio
async def test_synthesize_skips_llm_entirely_when_all_dupes():
    """Sentinel boundary: if every observation auto-merges, _call_primary_llm must not run.

    This is the whole point of the feature — LLM calls saved. If this regresses, the
    dedupe might be running but not actually short-circuiting.
    """
    existing = [
        {
            "id": "insight:existing",
            "content": "existing",
            "embedding": [1.0, 0.0, 0.0],
            "confidence": 0.7,
        }
    ]
    observations = [
        {"id": "obs:1", "content": "dup a", "confidence": 0.7, "discipline_hint": "architecture"},
        {"id": "obs:2", "content": "dup b", "confidence": 0.7, "discipline_hint": "architecture"},
    ]
    embeddings = {
        "dup a": [1.0, 0.0, 0.0],
        "dup b": [1.0, 0.0, 0.0],
    }

    synth = _mk_synth()
    synth._pending = list(observations)
    synth._load_existing_insights = AsyncMock(return_value=existing)
    synth._call_primary_llm = AsyncMock(return_value={"new_insights": [], "updates": [], "conflicts": []})
    synth._boost_insight_confidence = AsyncMock()

    with patch("core.engine.capture.synthesizer.get_embedder", return_value=_FakeEmbedder(embeddings)):
        result = await synth.synthesize()

    synth._call_primary_llm.assert_not_called()
    assert result["skipped"] == 2


@pytest.mark.asyncio
async def test_dedupe_failure_is_non_fatal():
    """If the embedder raises, fall back to passing all observations through."""
    existing = [{"id": "insight:x", "content": "x", "embedding": [1.0, 0.0, 0.0]}]
    observations = [{"id": "obs:1", "content": "anything"}]

    class _Broken:
        dimensions = 3

        async def embed(self, texts):
            raise RuntimeError("embedder down")

    synth = _mk_synth()
    with patch("core.engine.capture.synthesizer.get_embedder", return_value=_Broken()):
        non_matched, auto_merged = await synth._embedding_dedupe(observations, existing)

    assert non_matched == observations
    assert auto_merged == []
