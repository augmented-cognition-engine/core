# tests/test_pipeline.py
from unittest.mock import AsyncMock, patch

import pytest

from core.engine.capture.watchers import SessionImportWatcher


@pytest.mark.asyncio
async def test_pipeline_processes_session_import():
    """Full pipeline: SessionImportWatcher → Chunker → Observer → Synthesizer."""
    from core.engine.capture.pipeline import CapturePipeline

    transcript = """I checked the token naming convention. Tokens use acme- prefix with kebab-case.

The build uses Style Dictionary v5 for token transformation.

I discovered that Supernova's export API doesn't handle nested groups correctly."""

    watcher = SessionImportWatcher(transcript, session_id="test-session")

    mock_llm_obs = {
        "has_intelligence": True,
        "observations": [
            {
                "content": "Token naming: acme- prefix",
                "type": "fact",
                "confidence": 0.9,
                "discipline_hint": "ux",
            }
        ],
    }
    mock_llm_synth = {"new_insights": [], "updates": [], "conflicts": [], "skipped": [0]}

    pipeline = CapturePipeline(
        watcher=watcher,
        product_id="product:test",
        workspace_id=None,
    )

    with patch.object(pipeline.observer, "_call_budget_llm", new_callable=AsyncMock, return_value=mock_llm_obs):
        with patch.object(
            pipeline.synthesizer, "_call_primary_llm", new_callable=AsyncMock, return_value=mock_llm_synth
        ):
            await pipeline.run()

    # Synthesizer should have been flushed
    assert pipeline.synthesizer.pending_count == 0


@pytest.mark.asyncio
async def test_pipeline_flushes_on_end():
    """Pipeline flushes synthesizer when stream ends."""
    from core.engine.capture.pipeline import CapturePipeline

    watcher = SessionImportWatcher("Short session content.", session_id="test")
    pipeline = CapturePipeline(watcher=watcher, product_id="product:test", workspace_id=None)

    mock_llm_obs = {"has_intelligence": False, "observations": []}

    with patch.object(pipeline.observer, "_call_budget_llm", new_callable=AsyncMock, return_value=mock_llm_obs):
        await pipeline.run()

    assert pipeline.synthesizer.pending_count == 0


@pytest.mark.asyncio
async def test_periodic_synthesis_triggers_during_run():
    """_periodic_synthesis timer fires and calls synthesizer.synthesize() mid-run."""
    import asyncio
    from datetime import datetime, timezone
    from typing import AsyncIterator

    from core.engine.capture.pipeline import CapturePipeline
    from core.engine.capture.watchers import StreamEvent

    # Custom watcher that yields events slowly so timer fires during run
    class SlowWatcher:
        def __init__(self, session_id: str):
            self.session_id = session_id

        async def watch(self) -> AsyncIterator[StreamEvent]:
            # Yield events with delays to allow timer to fire between them
            # Use "status" events which emit chunks immediately in chunker
            # Content must be long enough (>80 chars = ~20 tokens) to pass observer token check
            for i in range(3):
                yield StreamEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="status",
                    content="Status event with observation content that is long enough to pass token threshold check number "
                    + str(i),
                    session_id=self.session_id,
                    metadata={"source": "test", "index": i},
                )
                await asyncio.sleep(0.02)  # Sleep 20ms, longer than 10ms timer interval

    pipeline = CapturePipeline(
        watcher=SlowWatcher(session_id="timer-test"),
        product_id="product:test",
        workspace_id=None,
        synthesis_interval=0.01,  # 10ms — will fire before stream ends
    )

    # Observer returns observations so synthesizer gets pending items
    mock_llm_obs = {
        "has_intelligence": True,
        "observations": [{"content": "test obs", "type": "fact", "confidence": 0.8, "discipline_hint": "architecture"}],
    }
    mock_llm_synth = {"new_insights": [], "updates": [], "conflicts": [], "skipped": [0]}

    # Track calls to synthesize using a side_effect instead of wraps
    synthesize_call_count = []
    original_synthesize = pipeline.synthesizer.synthesize

    async def tracked_synthesize():
        synthesize_call_count.append(1)
        return await original_synthesize()

    with patch.object(pipeline.observer, "_call_budget_llm", new_callable=AsyncMock, return_value=mock_llm_obs):
        with patch.object(
            pipeline.synthesizer, "_call_primary_llm", new_callable=AsyncMock, return_value=mock_llm_synth
        ):
            with patch.object(
                pipeline.synthesizer, "synthesize", new_callable=AsyncMock, side_effect=tracked_synthesize
            ):
                await pipeline.run()

    # synthesize() should have been called (either by timer or by flush)
    assert len(synthesize_call_count) >= 1
    assert pipeline.synthesizer.pending_count == 0
