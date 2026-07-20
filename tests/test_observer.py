# tests/test_observer.py
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.capture.watchers import Chunk, StreamEvent


def _chunk(content: str = "test content", chunk_type: str = "reasoning", tokens: int = 50) -> Chunk:
    evt = StreamEvent(timestamp=datetime.now(), event_type="text", content=content)
    return Chunk(
        content=content,
        chunk_type=chunk_type,
        events=[evt],
        start_time=datetime.now(),
        end_time=datetime.now(),
        token_count=tokens,
    )


@pytest.mark.asyncio
async def test_skips_tiny_chunks():
    """Observer skips chunks with < 20 tokens."""
    from core.engine.capture.observer import Observer

    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = _chunk(content="ok", tokens=5)
    observations = await observer.evaluate_chunk(chunk, memory_id=None)
    assert observations == []


@pytest.mark.asyncio
async def test_returns_observations_from_llm():
    """Observer returns observations when LLM finds intelligence."""
    from core.engine.capture.observer import Observer

    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = _chunk(
        content="I chose kebab-case over camelCase for token names because the existing convention uses it.",
        tokens=80,
    )

    mock_response = {
        "has_intelligence": True,
        "observations": [
            {
                "content": "Token naming convention: kebab-case chosen over camelCase",
                "type": "decision",
                "confidence": 0.85,
                "discipline_hint": "ux",
            }
        ],
    }

    with patch.object(observer, "_call_budget_llm", new_callable=AsyncMock, return_value=mock_response):
        observations = await observer.evaluate_chunk(chunk, memory_id=None)

    assert len(observations) == 1
    assert observations[0]["observation_type"] == "decision"
    assert observations[0]["confidence"] == 0.85


@pytest.mark.asyncio
async def test_returns_empty_when_no_intelligence():
    """Observer returns empty list when LLM finds nothing interesting."""
    from core.engine.capture.observer import Observer

    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = _chunk(content="Reading file contents", tokens=30)

    mock_response = {"has_intelligence": False, "observations": []}

    with patch.object(observer, "_call_budget_llm", new_callable=AsyncMock, return_value=mock_response):
        observations = await observer.evaluate_chunk(chunk, memory_id=None)

    assert observations == []
