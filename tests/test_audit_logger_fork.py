"""Verify AuditLogger fork-writes to both event_log and journey_event."""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_audit_logger_forks_to_journey_event():
    from core.engine.core.db import parse_rows, pool
    from core.engine.events.audit_logger import audit_logger
    from core.engine.events.bus import bus

    await pool.init()
    await audit_logger.start(pool)

    # Cleanup any prior test rows
    async with pool.connection() as db:
        await db.query("DELETE event_log WHERE event_type = 'test.fork_marker'")
        await db.query("DELETE journey_event WHERE topic = 'test.fork_marker'")

    try:
        # Emit a test event via the bus
        await bus.emit("test.fork_marker", {"marker": "abc123", "product_id": "product:platform"})

        # Allow async write
        await asyncio.sleep(0.2)

        async with pool.connection() as db:
            ev_rows = parse_rows(await db.query("SELECT id FROM event_log WHERE event_type = 'test.fork_marker'"))
            jr_rows = parse_rows(await db.query("SELECT id, topic FROM journey_event WHERE topic = 'test.fork_marker'"))
        assert len(ev_rows) == 1, f"event_log: expected 1, got {len(ev_rows)}"
        assert len(jr_rows) == 1, f"journey_event: expected 1, got {len(jr_rows)}"
        assert jr_rows[0]["topic"] == "test.fork_marker"
    finally:
        async with pool.connection() as db:
            await db.query("DELETE event_log WHERE event_type = 'test.fork_marker'")
            await db.query("DELETE journey_event WHERE topic = 'test.fork_marker'")
        await audit_logger.stop()
