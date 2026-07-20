"""Tests for duplicate and related detection on idea capture."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_tokenize_filters_stopwords():
    from core.engine.ideas.related import _tokenize

    tokens = _tokenize("The quick brown fox jumps over the lazy dog")
    assert "the" not in tokens
    assert "over" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens
    assert "fox" in tokens


def test_jaccard_similarity():
    from core.engine.ideas.related import jaccard_similarity

    # Identical texts
    assert jaccard_similarity("hello world", "hello world") == 1.0
    # No overlap
    assert jaccard_similarity("hello world", "foo bar baz") == 0.0
    # Partial overlap
    sim = jaccard_similarity("build webhook integration system", "build integration for slack webhooks")
    assert 0.3 < sim < 0.8
    # Empty text
    assert jaccard_similarity("", "hello") == 0.0


@pytest.mark.asyncio
async def test_find_similar_ideas():
    mock_conn = AsyncMock()
    mock_conn.query.return_value = [
        {
            "id": "idea:1",
            "title": "Build webhook integration",
            "raw_input": "webhook system for external sources",
            "status": "captured",
        },
        {
            "id": "idea:2",
            "title": "Improve dashboard layout",
            "raw_input": "redesign the portal dashboard",
            "status": "incubating",
        },
    ]
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.ideas.related.pool", mock_pool):
        from core.engine.ideas.related import find_similar_ideas

        results = await find_similar_ideas(
            "webhook integration for external platforms", "product:default", threshold=0.2
        )

    assert len(results) >= 1
    assert results[0]["title"] == "Build webhook integration"
    assert results[0]["similarity"] > 0.2


@pytest.mark.asyncio
async def test_find_similar_ideas_no_matches():
    mock_conn = AsyncMock()
    mock_conn.query.return_value = [
        {
            "id": "idea:1",
            "title": "Something completely different",
            "raw_input": "quantum computing research",
            "status": "captured",
        },
    ]
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.ideas.related.pool", mock_pool):
        from core.engine.ideas.related import find_similar_ideas

        results = await find_similar_ideas("webhook integration", "product:default", threshold=0.3)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_find_related_insights():
    mock_conn = AsyncMock()
    mock_conn.query.return_value = [
        {
            "id": "insight:1",
            "content": "Webhook integrations improve data capture efficiency",
            "confidence": 0.85,
            "domain_path": "architecture",
        },
        {
            "id": "insight:2",
            "content": "The CEO prefers quarterly reports",
            "confidence": 0.9,
            "domain_path": "business_logic",
        },
    ]
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("core.engine.ideas.related.pool", mock_pool):
        from core.engine.ideas.related import find_related_insights

        results = await find_related_insights("webhook integration for data capture", "architecture", "product:default")

    assert len(results) >= 1
    assert "webhook" in results[0]["content"].lower() or results[0]["similarity"] > 0
