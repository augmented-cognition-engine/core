# tests/test_decision_bridge.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_async_context_manager(return_value=None):
    """Return a MagicMock that behaves as an async context manager."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=return_value)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_db_pool(query_return=None):
    """Return a mock db_pool whose .connection() is an async context manager."""
    mock_db = AsyncMock()
    mock_db.query = AsyncMock(return_value=query_return or [{"id": "insight:test"}])
    pool = MagicMock()
    pool.connection = MagicMock(return_value=_make_async_context_manager(mock_db))
    return pool


@pytest.mark.asyncio
async def test_decision_insight_bridges_to_decision_table():
    """When synthesizer writes a decision insight, also creates a decision record and attaches prediction."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer.__new__(Synthesizer)
    synth.product_id = "product:default"
    synth.workspace_id = "workspace:default"
    synth._db_pool = _make_db_pool()
    synth._pending = []

    with patch("core.engine.capture.synthesizer.create_decision", new_callable=AsyncMock) as mock_decision:
        # Mock the returned decision record with an id
        mock_decision.return_value = {"id": "decision:test-123"}
        # Stub the atomic write (the insight row is not under test here) and the
        # best-effort prediction attach.
        with patch(
            "core.engine.capture.synthesizer.atomic_capture_write",
            new_callable=AsyncMock,
            return_value="insight:test-123",
        ):
            with patch("core.engine.foresight.forecaster.attach_prediction", new_callable=AsyncMock) as mock_prediction:
                await synth._write_insight(
                    {
                        "content": "Decided to use event-driven architecture",
                        "insight_type": "decision",
                        "confidence": 0.8,
                    },
                    observation_ids=["obs:1"],
                )

    mock_decision.assert_called_once()
    call_kwargs = mock_decision.call_args
    # Check that rationale contains the decision content
    assert "event-driven" in str(call_kwargs)
    # Verify that attach_prediction was called with the decision_id from the returned record
    mock_prediction.assert_called_once()
    pred_call_kwargs = mock_prediction.call_args
    assert pred_call_kwargs[1].get("decision_id") == "decision:test-123"


@pytest.mark.asyncio
async def test_non_decision_insight_does_not_bridge():
    """Non-decision insights don't create decision records."""
    from core.engine.capture.synthesizer import Synthesizer

    synth = Synthesizer.__new__(Synthesizer)
    synth.product_id = "product:default"
    synth.workspace_id = "workspace:default"
    synth._db_pool = _make_db_pool()
    synth._pending = []

    with patch("core.engine.capture.synthesizer.create_decision", new_callable=AsyncMock) as mock_decision:
        with patch(
            "core.engine.capture.synthesizer.atomic_capture_write",
            new_callable=AsyncMock,
            return_value="insight:test-456",
        ):
            await synth._write_insight(
                {
                    "content": "Python uses snake_case",
                    "insight_type": "fact",
                    "confidence": 0.9,
                },
                observation_ids=["obs:1"],
            )

    mock_decision.assert_not_called()
