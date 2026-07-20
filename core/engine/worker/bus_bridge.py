# engine/worker/bus_bridge.py
"""Bus bridge — persist worker signals then emit to canvas event bus.

Single emit point for all worker-sourced canvas events. Persist-first design:
worker_signal rows survive bus emit failures (bus.emit is fire-and-forget).
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool
from core.engine.events.bus import bus
from core.engine.worker.signals import SignalEmission

logger = logging.getLogger(__name__)

_KIND_TO_EVENT_TYPE: dict[str, str] = {
    "intelligence_classified": "canvas.intelligence.classified",
    "pattern_matched": "canvas.pattern.matched",
}


async def emit_signals_to_bus(signals: list[SignalEmission]) -> None:
    """Persist each signal to worker_signal, then emit to canvas bus.

    Persist FIRST — survives bus emit failures.
    bus.emit silently drops if no handler registered; that is intentional.
    """
    for signal in signals:
        event_type = _KIND_TO_EVENT_TYPE.get(signal.kind)
        if event_type is None:
            logger.warning("bus_bridge: unknown signal kind %s", signal.kind)
            continue

        # Persist FIRST — survives bus emit failures
        try:
            async with pool.connection() as db:
                await db.query(
                    """CREATE worker_signal CONTENT {
                        product: <record>$pid,
                        kind: <string>$kind,
                        event_type: <string>$evt,
                        payload: $payload,
                        confidence: <float>$conf,
                        emitted_at: time::now()
                    }""",
                    {
                        "pid": signal.product_id,
                        "kind": signal.kind,
                        "evt": event_type,
                        "payload": signal.payload,
                        "conf": signal.confidence,
                    },
                )
        except Exception as exc:
            logger.warning("bus_bridge: persist failed: %s", exc)
            # continue — try to emit anyway

        # Then emit
        try:
            await bus.emit(
                event_type,
                {
                    "product_id": signal.product_id,
                    "confidence": signal.confidence,
                    **signal.payload,
                },
            )
        except Exception as exc:
            logger.warning("bus_bridge: emit failed for %s: %s", signal.kind, exc)
