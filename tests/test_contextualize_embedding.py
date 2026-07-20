"""Contextual chunk enrichment — structural context prefix for embedding (no LLM, index-time).
See docs/superpowers/specs/2026-06-23-contextual-chunk-enrichment-design.md."""

from __future__ import annotations

from core.engine.capture.contextualize import contextualize_for_embedding


def test_prefixes_discipline_type_tags():
    out = contextualize_for_embedding(
        "use retry with backoff", domain_path="security", insight_type="pattern", tags=["error_handling"]
    )
    assert out == "[security · pattern · error_handling] use retry with backoff"


def test_no_context_returns_content_unchanged():
    assert contextualize_for_embedding("raw chunk") == "raw chunk"
    assert contextualize_for_embedding("raw chunk", domain_path="", insight_type=None, tags=[]) == "raw chunk"


def test_dedups_repeated_parts():
    out = contextualize_for_embedding("x", domain_path="security", insight_type="pattern", tags=["security"])
    assert out == "[security · pattern] x"  # 'security' not repeated


def test_comma_joined_domain_takes_first_segment():
    out = contextualize_for_embedding("x", domain_path="security,testing,observability", insight_type="fact")
    assert out == "[security · fact] x"


def test_prefix_length_capped():
    out = contextualize_for_embedding(
        "x", domain_path="security", insight_type="pattern", tags=["a", "b", "c", "d", "e"]
    )
    # cap at 4 parts: discipline + type + 2 tags
    assert out == "[security · pattern · a · b] x"


def test_only_domain_available():
    assert contextualize_for_embedding("x", domain_path="ux") == "[ux] x"


# ── worker hot-path embed site enriches too (review-found 4th site) ─────────────

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_worker_embed_new_insights_enriches(monkeypatch):
    """worker.processor.embed_new_insights (the hot-path embed that pre-empts the reconciler) must embed
    the SAME enriched text, else degraded-mode insights stay permanently unenriched."""
    import core.engine.core.config as cfg
    import core.engine.worker.processor as proc

    monkeypatch.setattr(cfg.settings, "contextual_chunk_enrichment", True, raising=False)

    captured: dict = {}

    class _Emb:
        dimensions = 3

        async def embed(self, texts):
            captured["texts"] = texts
            return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(proc, "get_embedder", lambda: _Emb())

    row = {
        "id": "insight:x",
        "content": "handle retries",
        "domain_path": "security",
        "insight_type": "pattern",
        "tags": ["error_handling"],
    }
    mock_pool = MagicMock()
    conn = MagicMock()

    async def q(query, params=None):
        return [[row]] if "SELECT" in query else [[]]

    conn.query = q
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(proc, "pool", mock_pool)

    n = await proc.embed_new_insights("product:test")
    assert n == 1
    assert captured["texts"] == ["[security · pattern · error_handling] handle retries"]
