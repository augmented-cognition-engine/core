from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_bus_bridge_persists_then_emits(db_pool):
    from core.engine.worker.bus_bridge import emit_signals_to_bus
    from core.engine.worker.signals import SignalEmission

    signals = [
        SignalEmission(
            kind="intelligence_classified",
            product_id="product:platform",
            payload={"discipline": "ux"},
            confidence=0.9,
        )
    ]

    with patch("core.engine.worker.bus_bridge.bus.emit", new=AsyncMock()) as mock_emit:
        await emit_signals_to_bus(signals)

    mock_emit.assert_called_once()
    call_args = mock_emit.call_args
    assert call_args.args[0] == "canvas.intelligence.classified"
    assert call_args.args[1]["discipline"] == "ux"

    # Confirm worker_signal row persisted
    from core.engine.core.db import parse_rows

    async with db_pool.connection() as db:
        rows = parse_rows(
            await db.query(
                """SELECT kind FROM worker_signal
               WHERE product = product:platform AND emitted_at > time::now() - 5s""",
            )
        )
    assert any(r["kind"] == "intelligence_classified" for r in rows)


@pytest.mark.asyncio
async def test_bus_bridge_skips_unknown_kind(caplog):
    from core.engine.worker.bus_bridge import emit_signals_to_bus
    from core.engine.worker.signals import SignalEmission

    bad = [
        SignalEmission(
            kind="not_a_real_kind",
            product_id="product:platform",
            payload={},
            confidence=0.5,
        )
    ]
    await emit_signals_to_bus(bad)
    # Should log warning, not crash
    assert any("unknown signal kind" in r.message.lower() for r in caplog.records)
