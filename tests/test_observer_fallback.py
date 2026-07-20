# tests/test_observer_fallback.py
"""Tests for observer LLM fallback path."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.capture.observer import Observer
from core.engine.capture.watchers import Chunk, StreamEvent


def _make_chunk(
    content="This is a test chunk with enough tokens to pass the threshold check for evaluation", chunk_type="text"
):
    events = [StreamEvent(timestamp=datetime.now(), event_type="text", content=content, session_id="s1")]
    return Chunk(
        events=events,
        chunk_type=chunk_type,
        content=content,
        token_count=50,
        start_time=datetime.now(),
        end_time=datetime.now(),
    )


@pytest.mark.asyncio
async def test_observer_structured_path_produces_valid_observations():
    """When complete_structured succeeds, observations are well-formed."""
    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = _make_chunk()

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "has_intelligence": True,
        "observations": [{"content": "a fact", "type": "fact", "confidence": 0.8, "discipline_hint": "tech"}],
    }

    with patch("core.engine.capture.observer.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_result)
        result = await observer.evaluate_chunk(chunk, "memory:1")

    assert len(result) == 1
    assert result[0]["observation_type"] == "fact"
    assert result[0]["content"] == "a fact"
    assert result[0]["source_memory"] == "memory:1"


@pytest.mark.asyncio
async def test_observer_fallback_produces_valid_observations():
    """When complete_structured fails, complete_json fallback still produces valid observations."""
    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = _make_chunk()

    with patch("core.engine.capture.observer.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(side_effect=Exception("structured failed"))
        mock_llm.complete_json = AsyncMock(
            return_value={
                "has_intelligence": True,
                "observations": [{"content": "test", "type": "fact", "confidence": 0.9, "discipline_hint": "tech"}],
            }
        )
        result = await observer.evaluate_chunk(chunk, None)

    assert len(result) == 1
    assert result[0]["observation_type"] == "fact"


@pytest.mark.asyncio
async def test_observer_fallback_skips_malformed_entries():
    """Fallback path skips observations missing required fields."""
    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = _make_chunk()

    with patch("core.engine.capture.observer.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(side_effect=Exception("fail"))
        mock_llm.complete_json = AsyncMock(
            return_value={
                "has_intelligence": True,
                "observations": [
                    {"content": "valid", "type": "fact", "confidence": 0.8},
                    {"content": "missing type"},  # no type field — should be skipped
                    {"type": "fact", "confidence": 0.5},  # no content — should be skipped
                ],
            }
        )
        result = await observer.evaluate_chunk(chunk, None)

    assert len(result) == 1
    assert result[0]["content"] == "valid"
