# tests/test_capture_idea.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.ideas.schemas import IdeaClassification


@pytest.mark.asyncio
async def test_capture_idea_returns_captured_status():
    """capture_idea returns an idea record with status='captured'."""
    from core.engine.ideas.capture import capture_idea

    mock_classification = IdeaClassification(
        domain_path="ux",
        type="feature",
        complexity="moderate",
        title="Multi-brand token architecture",
        summary="Support multiple brand themes in one token set.",
    )

    with patch("core.engine.ideas.capture.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_classification)
        with patch("core.engine.ideas.capture.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(
                return_value=[
                    [
                        {
                            "id": "idea:abc",
                            "status": "captured",
                            "raw_input": "What if we supported multi-brand themes?",
                            "title": "Multi-brand token architecture",
                            "classification": mock_classification.model_dump(),
                            "tags": ["experience", "design-systems"],
                        }
                    ]
                ]
            )
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await capture_idea(
                raw_input="What if we supported multi-brand themes?",
                user_id="user:ed",
                product_id="product:default",
            )

    assert result["status"] == "captured"
    assert result["title"] == "Multi-brand token architecture"


@pytest.mark.asyncio
async def test_capture_idea_classifies_with_budget_llm():
    """capture_idea calls complete_structured with IdeaClassification schema."""
    from core.engine.ideas.capture import capture_idea

    mock_classification = IdeaClassification(
        domain_path="architecture",
        type="research",
        complexity="simple",
        title="API caching layer",
        summary="Research caching strategies for the API.",
    )

    with patch("core.engine.ideas.capture.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_classification)
        with patch("core.engine.ideas.capture.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(
                return_value=[[{"id": "idea:xyz", "status": "captured", "title": "API caching layer"}]]
            )
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            await capture_idea(
                raw_input="Should we add a caching layer to the API?",
                user_id="user:ed",
                product_id="product:default",
            )

    mock_llm.complete_structured.assert_called_once()
    call_args = mock_llm.complete_structured.call_args
    assert call_args[0][1] is IdeaClassification


@pytest.mark.asyncio
async def test_capture_idea_minimal_input():
    """Single sentence idea is captured without error."""
    from core.engine.ideas.capture import capture_idea

    mock_classification = IdeaClassification(
        domain_path="architecture",
        type="other",
        complexity="simple",
        title="Logging improvements",
        summary="Improve logging.",
    )

    with patch("core.engine.ideas.capture.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_classification)
        with patch("core.engine.ideas.capture.pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.query = AsyncMock(
                return_value=[[{"id": "idea:min", "status": "captured", "title": "Logging improvements"}]]
            )
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await capture_idea(
                raw_input="Better logs",
                user_id="user:ed",
                product_id="product:default",
            )

    assert result["title"] == "Logging improvements"


@pytest.mark.asyncio
async def test_capture_idea_generates_tags_from_domain():
    """Tags are derived from the classification domain_path."""
    from core.engine.ideas.capture import capture_idea

    mock_classification = IdeaClassification(
        domain_path="ux.design-systems",
        type="feature",
        complexity="complex",
        title="Token pipeline v2",
        summary="Rebuild the token pipeline.",
    )

    with patch("core.engine.ideas.capture.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_classification)
        with patch("core.engine.ideas.capture.pool") as mock_pool:
            mock_conn = AsyncMock()

            async def check_query(query_str, params):
                if "CREATE idea" in query_str:
                    tags = params.get("tags", [])
                    assert "ux" in tags
                    assert "design-systems" in tags
                    return [[{"id": "idea:t1", "status": "captured", "title": "Token pipeline v2", "tags": tags}]]
                return [[]]

            mock_conn.query = check_query
            mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

            await capture_idea(
                raw_input="Rebuild the token pipeline",
                user_id="user:ed",
                product_id="product:default",
            )
