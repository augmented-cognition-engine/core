# engine/events/audit_logger.py
"""AuditLogger — persists bus events to event_log table for debugging and replay.

Subscribes to all events via wildcard ("*") registration on the singleton bus.
Keeps bus.py DB-free: persistence is a pluggable concern registered at startup.

Retention: 7-day rolling window enforced at write time (no separate cron needed).
Max practical volume: ~10k rows/week for an active ACE installation.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 7


class AuditLogger:
    """Subscribes to all bus events and writes them to the event_log table."""

    def __init__(self) -> None:
        self._pool = None
        self._running = False

    async def start(self, pool) -> None:
        """Wire into the event bus. Call once on application startup."""
        if self._running:
            return
        self._pool = pool
        from core.engine.events.bus import bus

        bus.on("*", self._handle)
        self._running = True
        logger.info("AuditLogger started — persisting all bus events to event_log")

    async def stop(self) -> None:
        """Unregister from the bus. Call on application shutdown."""
        if not self._running:
            return
        from core.engine.events.bus import bus

        bus.off("*", self._handle)
        self._running = False
        self._pool = None
        logger.info("AuditLogger stopped")

    async def _handle(self, event_type: str, payload: dict) -> None:
        """Write one event to event_log and trim old records."""
        if not self._pool:
            return
        try:
            product = payload.get("product_id") or payload.get("product") or None
            # Ensure payload is JSON-serialisable (handlers may put non-serialisable objects in)
            safe_payload = json.loads(json.dumps(payload, default=str))
            async with self._pool.connection() as db:
                await db.query(
                    """CREATE event_log SET
                           event_type = $event_type,
                           payload    = $payload,
                           product    = $product,
                           created_at = time::now()""",
                    {
                        "event_type": event_type,
                        "payload": safe_payload,
                        "product": product,
                    },
                )
                # Rolling retention — delete records older than 7 days
                await db.query(
                    "DELETE event_log WHERE created_at < time::now() - $days",
                    {"days": f"{_RETENTION_DAYS}d"},
                )
                # NEW: fork-write to journey_event (long retention; partner-history)
                # Best-effort — log on failure, don't raise (audit log is canonical).
                try:
                    # When bus emit comes from emit_canvas_event(), safe_payload is a
                    # serialized LivingCanvasEvent dict with shape
                    # {event_type, payload, provenance, ...}. Extract the inner caller
                    # payload so journey_event.payload is always the flat user payload,
                    # not a nested wrapper. Bare bus events (gap.detected etc.) don't
                    # have this nesting — fall through to safe_payload directly.
                    inner_payload = safe_payload
                    inner_provenance = None
                    if isinstance(safe_payload, dict):
                        if "event_type" in safe_payload and "payload" in safe_payload:
                            inner_payload = safe_payload.get("payload") or {}
                        inner_provenance = safe_payload.get("provenance")

                    if product is not None:
                        await db.query(
                            """CREATE journey_event SET
                                   topic      = $topic,
                                   product    = <record>$product,
                                   payload    = $payload,
                                   provenance = $provenance,
                                   occurred_at = time::now()""",
                            {
                                "topic": event_type,
                                "product": product,
                                "payload": inner_payload,
                                "provenance": inner_provenance,
                            },
                        )
                except Exception as fork_exc:
                    logger.debug("AuditLogger journey_event fork failed for %s: %s", event_type, fork_exc)
        except Exception as exc:
            # Never raise — audit failure must not affect event handlers
            logger.debug("AuditLogger write failed for %s: %s", event_type, exc)


# Singleton
audit_logger = AuditLogger()
