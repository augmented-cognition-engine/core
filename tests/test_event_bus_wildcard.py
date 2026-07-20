# tests/test_event_bus_wildcard.py
"""Tests for wildcard ("*") handler support added to EventBus."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.engine.events.bus import EventBus


@pytest.mark.asyncio
async def test_wildcard_handler_receives_all_events():
    """Handler registered on "*" receives every emitted event."""
    bus = EventBus()
    received: list[tuple[str, dict]] = []

    async def catch_all(event_type: str, payload: dict) -> None:
        received.append((event_type, payload))

    bus.on("*", catch_all)
    await bus.emit("foo.bar", {"x": 1})
    await bus.emit("baz.qux", {"y": 2})
    await asyncio.sleep(0.05)  # let background tasks complete

    assert len(received) == 2
    assert received[0] == ("foo.bar", {"x": 1})
    assert received[1] == ("baz.qux", {"y": 2})


@pytest.mark.asyncio
async def test_specific_and_wildcard_both_fire():
    """Specific handler AND wildcard handler both receive the same event."""
    bus = EventBus()
    specific_calls: list[dict] = []
    wildcard_calls: list[str] = []

    async def specific(event_type: str, payload: dict) -> None:
        specific_calls.append(payload)

    async def catch_all(event_type: str, payload: dict) -> None:
        wildcard_calls.append(event_type)

    bus.on("my.event", specific)
    bus.on("*", catch_all)

    await bus.emit("my.event", {"val": 42})
    await asyncio.sleep(0.05)

    assert specific_calls == [{"val": 42}]
    assert wildcard_calls == ["my.event"]


@pytest.mark.asyncio
async def test_wildcard_off_stops_delivery():
    """Unregistering the wildcard handler stops it from receiving events."""
    bus = EventBus()
    calls: list[str] = []

    async def catch_all(event_type: str, payload: dict) -> None:
        calls.append(event_type)

    bus.on("*", catch_all)
    await bus.emit("first", {})
    await asyncio.sleep(0.05)

    bus.off("*", catch_all)
    await bus.emit("second", {})
    await asyncio.sleep(0.05)

    assert calls == ["first"]


@pytest.mark.asyncio
async def test_wildcard_only_no_specific_handler():
    """If only a wildcard handler exists, the event is still dispatched."""
    bus = EventBus()
    received: list[str] = []

    async def catch_all(event_type: str, payload: dict) -> None:
        received.append(event_type)

    bus.on("*", catch_all)
    await bus.emit("unregistered.event", {"a": 1})
    await asyncio.sleep(0.05)

    assert "unregistered.event" in received


@pytest.mark.asyncio
async def test_audit_logger_uses_wildcard(monkeypatch):
    """AuditLogger subscribes to bus via '*' and writes events to DB pool."""
    import sys

    from core.engine.events.audit_logger import AuditLogger

    logger = AuditLogger()

    written: list[dict] = []

    async def fake_query(sql, params=None):
        written.append({"sql": sql, "params": params or {}})
        return []

    mock_db = MagicMock()
    mock_db.query = fake_query
    mock_conn = MagicMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_db)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(return_value=mock_conn)

    # Patch the module-level bus singleton via sys.modules
    bus_module = sys.modules["core.engine.events.bus"]
    fresh_bus = EventBus()
    monkeypatch.setattr(bus_module, "bus", fresh_bus)

    await logger.start(mock_pool)
    await fresh_bus.emit("test.event", {"key": "value"})
    await asyncio.sleep(0.05)

    # At least one CREATE event_log write should have happened
    create_writes = [w for w in written if "CREATE event_log" in w["sql"]]
    assert create_writes, "Expected AuditLogger to write to event_log table"

    await logger.stop()
