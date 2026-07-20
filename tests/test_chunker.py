# tests/test_chunker.py
from datetime import datetime

import pytest

from core.engine.capture.watchers import StreamEvent


def _event(event_type: str = "text", content: str = "hello", **kw) -> StreamEvent:
    return StreamEvent(timestamp=datetime.now(), event_type=event_type, content=content, **kw)


@pytest.mark.asyncio
async def test_emits_on_tool_result():
    """Chunker emits when a tool_result event arrives."""
    from core.engine.capture.chunker import Chunker

    chunker = Chunker()
    events = [
        _event("tool_use", "read_file /foo"),
        _event("tool_result", '{"content": "bar"}'),
    ]

    async def gen():
        for e in events:
            yield e

    chunks = []
    async for chunk, _ in chunker.process(gen()):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "action"


@pytest.mark.asyncio
async def test_emits_on_token_threshold():
    """Chunker emits when token count exceeds 500."""
    from core.engine.capture.chunker import Chunker

    chunker = Chunker()
    # ~600 tokens of text
    long_text = "word " * 600

    async def gen():
        yield _event("text", long_text)

    chunks = []
    async for chunk, _ in chunker.process(gen()):
        chunks.append(chunk)

    assert len(chunks) >= 1
    assert chunks[0].chunk_type == "reasoning"


@pytest.mark.asyncio
async def test_emits_on_status_change():
    """Chunker emits when status event arrives."""
    from core.engine.capture.chunker import Chunker

    chunker = Chunker()

    async def gen():
        yield _event("text", "thinking about things")
        yield _event("status", "waiting_for_user")

    chunks = []
    async for chunk, _ in chunker.process(gen()):
        chunks.append(chunk)

    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_chunk_type_error():
    """Chunks with error events are typed as error."""
    from core.engine.capture.chunker import Chunker

    chunker = Chunker()

    async def gen():
        yield _event("error", "something broke")

    chunks = []
    async for chunk, _ in chunker.process(gen()):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "error"


@pytest.mark.asyncio
async def test_skips_tiny_chunks():
    """Chunks with < 20 tokens are still emitted but flagged."""
    from core.engine.capture.chunker import Chunker

    chunker = Chunker()

    async def gen():
        yield _event("text", "ok")
        yield _event("status", "done")

    chunks = []
    async for chunk, _ in chunker.process(gen()):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0].token_count < 20


@pytest.mark.asyncio
async def test_emits_on_topic_shift():
    """Chunker emits when topic-shift phrase is detected."""
    from core.engine.capture.chunker import Chunker

    chunker = Chunker()

    async def gen():
        yield _event("text", "I fixed the bug in the auth module.")
        yield _event("text", "Moving on to the next feature now.")

    chunks = []
    async for chunk, _ in chunker.process(gen()):
        chunks.append(chunk)

    # The second event has "moving on" which triggers a topic shift emission
    assert len(chunks) >= 1
