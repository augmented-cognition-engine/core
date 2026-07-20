# tests/test_agent_sdk_watcher.py
import pytest

from core.engine.capture.watchers import StreamWatcher


@pytest.mark.asyncio
async def test_agent_sdk_watcher_satisfies_protocol():
    """AgentSDKWatcher implements StreamWatcher protocol."""
    from core.engine.capture.agent_sdk_watcher import AgentSDKWatcher

    async def empty_stream():
        return
        yield  # make it an async generator

    watcher = AgentSDKWatcher(sdk_stream=empty_stream(), session_id="test-session")
    assert isinstance(watcher, StreamWatcher)


@pytest.mark.asyncio
async def test_agent_sdk_watcher_maps_text_delta():
    """Text delta events become StreamEvent(event_type='text')."""
    from core.engine.capture.agent_sdk_watcher import AgentSDKWatcher

    async def mock_stream():
        yield {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Hello world"},
            },
        }

    watcher = AgentSDKWatcher(sdk_stream=mock_stream(), session_id="test")
    events = []
    async for event in watcher.watch():
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "text"
    assert events[0].content == "Hello world"
    assert events[0].session_id == "test"


@pytest.mark.asyncio
async def test_agent_sdk_watcher_maps_tool_use():
    """Tool use input_json_delta events become StreamEvent(event_type='tool_use')."""
    from core.engine.capture.agent_sdk_watcher import AgentSDKWatcher

    async def mock_stream():
        yield {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "input_json_delta", "partial_json": '{"file": "test.py"}'},
            },
        }

    watcher = AgentSDKWatcher(sdk_stream=mock_stream(), session_id="test")
    events = []
    async for event in watcher.watch():
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "tool_use"
    assert events[0].content == '{"file": "test.py"}'


@pytest.mark.asyncio
async def test_agent_sdk_watcher_maps_block_stop():
    """content_block_stop events become StreamEvent(event_type='status')."""
    from core.engine.capture.agent_sdk_watcher import AgentSDKWatcher

    async def mock_stream():
        yield {"type": "stream_event", "event": {"type": "content_block_stop"}}

    watcher = AgentSDKWatcher(sdk_stream=mock_stream(), session_id="test")
    events = []
    async for event in watcher.watch():
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "status"
    assert events[0].content == "block_complete"


@pytest.mark.asyncio
async def test_agent_sdk_watcher_maps_message_stop():
    """message_stop events become StreamEvent(event_type='status', content='message_complete')."""
    from core.engine.capture.agent_sdk_watcher import AgentSDKWatcher

    async def mock_stream():
        yield {"type": "stream_event", "event": {"type": "message_stop"}}

    watcher = AgentSDKWatcher(sdk_stream=mock_stream(), session_id="test")
    events = []
    async for event in watcher.watch():
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "status"
    assert events[0].content == "message_complete"


@pytest.mark.asyncio
async def test_agent_sdk_watcher_skips_non_stream_events():
    """Non-stream_event messages are skipped."""
    from core.engine.capture.agent_sdk_watcher import AgentSDKWatcher

    async def mock_stream():
        yield {"type": "result", "result": "done"}
        yield {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "only this"},
            },
        }

    watcher = AgentSDKWatcher(sdk_stream=mock_stream(), session_id="test")
    events = []
    async for event in watcher.watch():
        events.append(event)

    assert len(events) == 1
    assert events[0].content == "only this"
