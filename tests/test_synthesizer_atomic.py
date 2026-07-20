"""Synthesizer._write_insight routes through atomic_capture_write with an embedding."""

from unittest.mock import patch

import pytest

from core.engine.capture.synthesizer import Synthesizer


@pytest.mark.asyncio
async def test_write_insight_calls_atomic_write_with_embedding():
    from core.engine.capture import synthesizer as syn

    captured = {}

    async def fake_atomic(db_pool, *, insight_fields, embedding, specialty_slug, observation_ids):
        captured["embedding"] = embedding
        captured["content"] = insight_fields.get("content")
        captured["observation_ids"] = observation_ids
        return "insight:fake123"

    class FakeEmbedder:
        dimensions = 768

        async def embed(self, texts):
            return [[0.02] * 768 for _ in texts]

    s = Synthesizer.__new__(Synthesizer)
    s._db_pool = object()  # truthy; never used (atomic_capture_write is patched)
    s.product_id = "product:test"
    s.workspace_id = "workspace:test"

    with (
        patch.object(syn, "atomic_capture_write", side_effect=fake_atomic),
        patch.object(syn, "get_embedder", return_value=FakeEmbedder()),
    ):
        # No discipline/domain_path -> domain-resolution DB block is skipped.
        await s._write_insight(
            {"content": "webhook retries backoff unique-31459", "insight_type": "fact", "confidence": 0.7},
            ["observation:abc"],
        )

    assert captured["content"] == "webhook retries backoff unique-31459"
    assert captured["embedding"] is not None and len(captured["embedding"]) == 768
    assert captured["observation_ids"] == ["observation:abc"]
