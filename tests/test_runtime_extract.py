"""Tests for auto-extraction — event-driven capture delegation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.engine.runtime.auto_extract import AutoExtractor
from core.engine.runtime.models import AssistantMessage, UserMessage


@pytest.mark.asyncio
async def test_extract_skips_short_turns():
    extractor = AutoExtractor(product_id="product:test")
    messages = [
        UserMessage(content="hi"),
        AssistantMessage(content="Hello!", model="mock"),
    ]
    observations = await extractor.extract(messages)
    assert observations == []


@pytest.mark.asyncio
async def test_extract_emits_event_for_long_turns():
    """Long turns should emit a turn_for_capture event."""
    extractor = AutoExtractor(product_id="product:test")
    messages = [
        UserMessage(content="fix the SQL injection in login.py " + "x" * 100),
        AssistantMessage(
            content="I found a SQL injection vulnerability. Used parameterized queries to fix it. " + "y" * 100,
            model="mock",
        ),
    ]

    emitted_events = []

    async def mock_emit(event_name, payload):
        emitted_events.append((event_name, payload))

    mock_bus = MagicMock()
    mock_bus.emit = mock_emit

    with patch("core.engine.runtime.auto_extract.event_bus", mock_bus):
        result = await extractor.extract(messages)

    # Returns empty list — capture pipeline handles actual observations
    assert result == []
    # Should have emitted turn_for_capture event
    event_names = [e[0] for e in emitted_events]
    assert "runtime.turn_for_capture" in event_names

    # Event payload should include product_id and turn text
    turn_event = next(e[1] for e in emitted_events if e[0] == "runtime.turn_for_capture")
    assert turn_event["product_id"] == "product:test"
    assert "SQL injection" in turn_event["turn_text"]


@pytest.mark.asyncio
async def test_extract_returns_empty_always():
    """extract() always returns [] — capture pipeline owns observations."""
    extractor = AutoExtractor(product_id="product:test")
    messages = [
        UserMessage(content="do something complex " + "x" * 100),
        AssistantMessage(content="Done with detailed work. " + "y" * 100, model="mock"),
    ]
    with patch("core.engine.runtime.auto_extract.event_bus", None):
        result = await extractor.extract(messages)
    assert result == []


@pytest.mark.asyncio
async def test_extract_skips_empty_messages():
    extractor = AutoExtractor(product_id="product:test")
    observations = await extractor.extract([])
    assert observations == []


@pytest.mark.asyncio
async def test_fire_and_forget_does_not_block():
    extractor = AutoExtractor(product_id="product:test")
    messages = [
        UserMessage(content="do something complex"),
        AssistantMessage(content="Done with detailed work.", model="mock"),
    ]
    # fire_and_forget should return immediately
    with patch.object(extractor, "extract", new_callable=AsyncMock) as mock:
        mock.return_value = []
        extractor.fire_and_forget(messages)
        # Should not raise, should not block


@pytest.mark.asyncio
async def test_extract_no_event_bus_is_safe():
    """When event_bus is None, extract should not raise."""
    extractor = AutoExtractor(product_id="product:test")
    messages = [
        UserMessage(content="fix the auth bug in the system " + "x" * 100),
        AssistantMessage(content="Fixed the auth bug successfully. " + "y" * 100, model="mock"),
    ]
    with patch("core.engine.runtime.auto_extract.event_bus", None):
        result = await extractor.extract(messages)
    assert result == []
