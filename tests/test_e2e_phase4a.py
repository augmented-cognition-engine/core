# tests/test_e2e_phase4a.py
"""End-to-end tests for Phase 4a execution architecture."""

import pytest

pytestmark = pytest.mark.e2e
from datetime import datetime
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_e2e_classify_and_execute():
    """Full pipeline: classify returns dict -> loader uses mode -> executor builds archetype prompt."""
    from core.engine.orchestrator.executor import execute_task

    classification = {
        "discipline": "ux",
        "archetype": "creator",
        "mode": "deliberative",
        "complexity": "moderate",
        "specialties": [],
        "engagement": {"perspectives": ["practitioner"], "adversarial_pair": None, "rationale": ""},
    }

    mock_snapshot = {
        "discipline": "ux",
        "insights": [
            {
                "content": "Use kebab-case for tokens",
                "confidence": 0.9,
                "tier": "subdomain",
                "insight_type": "convention",
                "id": "insight:1",
            }
        ],
        "total_count": 1,
        "recent_signals": [
            {"content": "APCA replacing WCAG contrast", "observation_type": "discovery", "confidence": 0.8}
        ],
        "raw_context": [],
    }

    with patch("core.engine.orchestrator.executor.classify_task", new_callable=AsyncMock, return_value=classification):
        with patch(
            "core.engine.orchestrator.executor.load_intelligence", new_callable=AsyncMock, return_value=mock_snapshot
        ) as mock_loader:
            with patch("core.engine.orchestrator.executor.llm") as mock_llm:
                mock_llm.complete = AsyncMock(return_value="Design token output created.")
                with patch("core.engine.orchestrator.executor.pool") as mock_pool:
                    mock_conn = AsyncMock()
                    mock_conn.query = AsyncMock(return_value=[{"id": "task:e2e1"}])
                    mock_pool.connection.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
                    mock_pool.connection.return_value.__aexit__ = AsyncMock(return_value=False)

                    result = await execute_task(
                        "Create a new color token set", "product:test", "workspace:test", "user:test"
                    )

    # Verify discipline was passed to loader (adjacent_disciplines=None when confidence is high)
    mock_loader.assert_called_once_with(
        "ux", "product:test", mode="deliberative", specialties=[], adjacent_disciplines=None
    )

    # Verify archetype in result
    assert result["archetype"] == "creator"
    assert result["mode"] == "deliberative"

    # Verify recent signals were included in prompt
    prompt_used = mock_llm.complete.call_args[0][0]
    assert "Recent Observations" in prompt_used
    assert "APCA" in prompt_used


@pytest.mark.asyncio
async def test_e2e_structured_observer():
    """Observer produces validated output via complete_structured."""
    from core.engine.capture.observer import Observer
    from core.engine.capture.schemas import ObservationItem, ObserverOutput
    from core.engine.capture.watchers import Chunk, StreamEvent

    observer = Observer(product_id="product:test", workspace_id=None)
    chunk = Chunk(
        content="Switched from WCAG 2.1 to APCA for contrast checking",
        chunk_type="reasoning",
        events=[StreamEvent(timestamp=datetime.now(), event_type="text", content="test")],
        start_time=datetime.now(),
        end_time=datetime.now(),
        token_count=80,
    )

    mock_output = ObserverOutput(
        has_intelligence=True,
        observations=[ObservationItem(content="Switched to APCA contrast", type="correction", confidence=0.9)],
    )

    with patch("core.engine.capture.observer.llm") as mock_llm:
        mock_llm.complete_structured = AsyncMock(return_value=mock_output)
        observations = await observer.evaluate_chunk(chunk, memory_id=None)

    assert len(observations) == 1
    assert observations[0]["observation_type"] == "correction"
    assert observations[0]["confidence"] == 0.9
