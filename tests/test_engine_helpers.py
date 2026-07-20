# tests/test_engine_helpers.py
"""Tests for shared engine helpers: write_engine_insight, queue_research."""

from unittest.mock import AsyncMock

import pytest


def _make_engine_mock(*final_return):
    """Create a mock DB that returns empty for resolution queries and final_return for CREATE."""
    calls = []

    async def side_effect(query, params=None):
        calls.append(query)
        if "CREATE insight" in query:
            return list(final_return) if final_return else [{"id": "insight:mock"}]
        if "CREATE research_queue" in query:
            return list(final_return) if final_return else [{"id": "research_queue:mock"}]
        if "domain_flow_config" in query:
            return []
        # Resolution queries (domain, subdomain, specialty) return empty
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=side_effect)
    mock_db._calls = calls
    return mock_db


@pytest.mark.asyncio
async def test_write_engine_insight_creates_insight():
    """write_engine_insight should CREATE an insight record with provenance fields."""
    from core.engine.sentinel.engines import write_engine_insight

    mock_db = _make_engine_mock({"id": "insight:test123"})

    result = await write_engine_insight(
        db=mock_db,
        product_id="product:default",
        content="React 19 uses a compiler, not runtime reconciliation",
        insight_type="correction",
        tier="specialty",
        discipline="frontend",
        source_domain="sentinel.failure-analysis",
        confidence=0.85,
        tags=["auto-correction", "knowledge_gap"],
        source_task="task:abc",
    )

    assert result == "insight:test123"
    create_call = mock_db.query.call_args_list[-1]
    query_str = create_call[0][0]
    assert "CREATE insight" in query_str
    assert "source_domain" in query_str
    assert "domain" in query_str
    assert "specialty" in query_str


@pytest.mark.asyncio
async def test_write_engine_insight_without_source_task():
    """write_engine_insight works without a source_task."""
    from core.engine.sentinel.engines import write_engine_insight

    mock_db = _make_engine_mock({"id": "insight:test456"})

    result = await write_engine_insight(
        db=mock_db,
        product_id="product:default",
        content="GraphQL federation requires a gateway service",
        insight_type="fact",
        tier="subdomain",
        discipline="backend",
        source_domain="sentinel.gap-researcher",
        confidence=0.7,
        tags=["auto-researched"],
    )

    assert result == "insight:test456"


@pytest.mark.asyncio
async def test_write_engine_insight_discipline_in_tags():
    """write_engine_insight should include discipline in tags for queryability."""
    from core.engine.sentinel.engines import write_engine_insight

    written_params = {}

    async def capture_side_effect(query, params=None):
        if "CREATE insight" in query:
            written_params.update(params or {})
            return [{"id": "insight:fc789"}]
        return []

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(side_effect=capture_side_effect)

    result = await write_engine_insight(
        db=mock_db,
        product_id="product:default",
        content="Test insight",
        insight_type="fact",
        tier="subdomain",
        discipline="compliance",
        source_domain="sentinel.gap-researcher",
        confidence=0.6,
        tags=["auto-researched"],
    )

    assert result == "insight:fc789"
    # discipline should be prepended to tags
    assert "compliance" in written_params.get("tags", [])


@pytest.mark.asyncio
async def test_queue_research_creates_record():
    """queue_research should CREATE a research_queue record."""
    from core.engine.sentinel.engines import queue_research

    mock_db = _make_engine_mock({"id": "research_queue:rq1"})

    result = await queue_research(
        db=mock_db,
        product_id="product:default",
        query="What are the latest React Server Components patterns?",
        context="Failure in task:abc — used client components where server was needed",
        priority="high",
        source="failure-analysis",
        related_task="task:abc",
    )

    assert result == "research_queue:rq1"
    mock_db.query.assert_called_once()
    call_args = mock_db.query.call_args
    query_str = call_args[0][0]
    assert "CREATE research_queue" in query_str


@pytest.mark.asyncio
async def test_queue_research_without_related_task():
    """queue_research works without a related_task."""
    from core.engine.sentinel.engines import queue_research

    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=[[{"id": "research_queue:rq2"}]])

    result = await queue_research(
        db=mock_db,
        product_id="product:default",
        query="Best practices for Kubernetes pod autoscaling",
        context="Thin specialty: devops.kubernetes",
        priority="medium",
        source="specialty-deepener",
    )

    assert result == "research_queue:rq2"
