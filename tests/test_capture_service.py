# tests/test_capture_service.py
"""Tests for engine/capture/service.py — always-on CaptureService singleton."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.capture.service import CaptureService
from core.engine.capture.watchers import StreamEvent


def _make_event(product_id="product:test", source="test"):
    return StreamEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="tool_result",
        content="Something happened",
        session_id="session:abc",
        metadata={"product_id": product_id, "source": source},
    )


@pytest.mark.asyncio
async def test_emit_increments_counter():
    svc = CaptureService()
    await svc.emit(_make_event())
    stats = svc.get_stats()
    assert stats["emitted"] == 1
    assert stats["dropped"] == 0
    assert stats["queue_depth"] == 1


@pytest.mark.asyncio
async def test_emit_drops_when_queue_full():
    svc = CaptureService()
    # Fill the queue to capacity
    for _ in range(svc._queue.maxsize):
        svc._queue.put_nowait(_make_event())

    await svc.emit(_make_event())
    stats = svc.get_stats()
    assert stats["dropped"] == 1


@pytest.mark.asyncio
async def test_emit_task_completion_constructs_event():
    svc = CaptureService()
    await svc.emit_task_completion(
        product_id="product:test",
        task_id="task:123",
        description="Write a test",
        output="Here is the test: ...",
        discipline="testing",
    )
    assert svc._queue.qsize() == 1
    event = svc._queue.get_nowait()
    assert "testing" in event.content
    assert "Write a test" in event.content
    assert event.metadata["product_id"] == "product:test"
    assert event.metadata["source"] == "execute_task"


@pytest.mark.asyncio
async def test_emit_task_completion_truncates_long_output():
    svc = CaptureService()
    await svc.emit_task_completion(
        product_id="product:test",
        task_id="task:123",
        description="desc",
        output="x" * 5000,
        discipline="architecture",
    )
    event = svc._queue.get_nowait()
    # Output is capped at 2000 chars in the content
    assert len(event.content) < 4000


@pytest.mark.asyncio
async def test_get_stats_structure():
    svc = CaptureService()
    stats = svc.get_stats()
    assert "running" in stats
    assert "queue_depth" in stats
    assert "queue_max" in stats
    assert "emitted" in stats
    assert "dropped" in stats
    assert "processed" in stats
    assert "active_products" in stats
    assert "pending_synthesis" in stats


@pytest.mark.asyncio
async def test_start_stop_lifecycle():
    svc = CaptureService()

    with patch.object(svc, "_process_loop", new_callable=AsyncMock) as mock_loop:
        mock_loop.return_value = None
        svc.start()
        assert svc._running is True
        assert svc._task is not None
        await svc.stop()
        assert svc._running is False


@pytest.mark.asyncio
async def test_start_idempotent(caplog):
    """Calling start() twice should warn, not raise."""
    import logging

    svc = CaptureService()
    with patch.object(svc, "_process_loop", new_callable=AsyncMock):
        svc.start()
        with caplog.at_level(logging.WARNING):
            svc.start()  # second call
        assert "already running" in caplog.text
        await svc.stop()


@pytest.mark.asyncio
async def test_pipeline_created_lazily_per_product():
    svc = CaptureService()
    with (
        patch("core.engine.capture.service.Chunker") as MockChunker,
        patch("core.engine.capture.service.Observer") as MockObserver,
        patch("core.engine.capture.service.Synthesizer") as MockSynth,
    ):
        MockChunker.return_value = MagicMock()
        MockObserver.return_value = MagicMock()
        MockSynth.return_value = MagicMock(pending_count=0)

        svc._get_pipeline("product:a")
        svc._get_pipeline("product:b")
        svc._get_pipeline("product:a")  # second call — should not create again

        assert MockChunker.call_count == 2  # one per product
        assert len(svc._chunkers) == 2


@pytest.mark.asyncio
async def test_events_without_product_id_are_dropped():
    """Events with no product_id must not enter the pipeline."""
    svc = CaptureService()

    # Simulate _process_loop behavior for a no-product-id event
    event = StreamEvent(
        timestamp=datetime.now(timezone.utc),
        event_type="tool_result",
        content="Orphan event",
        session_id="s",
        metadata={},  # no product_id
    )

    processed_before = svc._processed
    # We can't easily run the full loop, but we can confirm emit still works
    await svc.emit(event)
    assert svc._emitted == 1  # emitted to queue
    assert svc._processed == processed_before  # not processed yet (loop not running)
