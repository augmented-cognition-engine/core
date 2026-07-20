# engine/capture/service.py
"""CaptureService — singleton always-on observation writer.

Replaces session-scoped CapturePipeline as the primary capture path.
Any part of the system can emit an event via capture_service.emit()
without knowing anything about Chunker, Observer, or Synthesizer.

Architecture:
    producer (execute_task, bus, MCP hooks)
        → capture_service.emit(StreamEvent)
        → internal asyncio.Queue
        → Chunker → Observer → Synthesizer → insight table

The service starts at app startup and runs until shutdown.
One instance handles all products — product_id travels with each event
via session_id or metadata["product_id"].
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from core.engine.capture.chunker import Chunker
from core.engine.capture.observer import Observer
from core.engine.capture.synthesizer import Synthesizer
from core.engine.capture.watchers import StreamEvent

logger = logging.getLogger(__name__)

_QUEUE_MAX = 2000
_SYNTHESIS_INTERVAL = 600  # 10 minutes — shorter than session pipeline (was 15)


class CaptureService:
    """Always-on observation writer. One instance per application process.

    Accepts events from any producer via emit(). Internally drives
    Chunker → Observer → Synthesizer without any session lifecycle.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._running = False
        self._task: asyncio.Task | None = None
        self._db_pool = None
        # Per-product pipeline components, keyed by product_id
        self._chunkers: dict[str, Chunker] = {}
        self._observers: dict[str, Observer] = {}
        self._synthesizers: dict[str, Synthesizer] = {}
        # Stats
        self._emitted = 0
        self._dropped = 0
        self._processed = 0

    def _get_pipeline(self, product_id: str, workspace_id: str | None = None):
        """Lazily create per-product pipeline components."""
        if product_id not in self._chunkers:
            chunker = Chunker()
            if self._db_pool:
                chunker._db_pool = self._db_pool
                chunker._org_id = product_id
            self._chunkers[product_id] = chunker

        if product_id not in self._observers:
            self._observers[product_id] = Observer(product_id, workspace_id)

        if product_id not in self._synthesizers:
            synth = Synthesizer(product_id, workspace_id)
            if self._db_pool:
                synth._db_pool = self._db_pool
            self._synthesizers[product_id] = synth

        return (
            self._chunkers[product_id],
            self._observers[product_id],
            self._synthesizers[product_id],
        )

    async def emit(self, event: StreamEvent) -> None:
        """Accept an observation event. Fire-and-forget — never blocks the caller."""
        try:
            self._queue.put_nowait(event)
            self._emitted += 1
            source = (event.metadata or {}).get("source", "unknown")
            try:
                from core.engine.core.metrics import capture_events_total, capture_queue_depth

                capture_events_total.labels(source=source).inc()
                capture_queue_depth.set(self._queue.qsize())
            except Exception:
                pass
        except asyncio.QueueFull:
            self._dropped += 1
            logger.warning(
                "CaptureService queue full (%d capacity), dropping event type=%s",
                _QUEUE_MAX,
                event.event_type,
            )
            try:
                from core.engine.core.metrics import capture_dropped_total

                capture_dropped_total.inc()
            except Exception:
                pass

    async def emit_task_completion(
        self,
        product_id: str,
        task_id: str,
        description: str,
        output: str,
        discipline: str,
        status: str = "completed",
        workspace_id: str | None = None,
    ) -> None:
        """Convenience method: emit a task completion as a capture event.

        Called from execute_task after output is written to DB.
        Packages task context into a StreamEvent so the pipeline can
        evaluate whether there's intelligence worth capturing.
        """
        content = f"Task [{discipline}]: {description}\n\nOutput: {output[:2000]}"
        event = StreamEvent(
            timestamp=datetime.now(timezone.utc),
            event_type="tool_result",
            content=content,
            session_id=task_id,
            metadata={
                "product_id": product_id,
                "workspace_id": workspace_id,
                "task_id": task_id,
                "discipline": discipline,
                "status": status,
                "source": "execute_task",
            },
        )
        await self.emit(event)

    async def _process_loop(self) -> None:
        """Main processing loop. Pulls events from queue and drives the pipeline."""
        logger.info("CaptureService started")
        synthesis_timers: dict[str, float] = {}

        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                # Periodic synthesis for all active products
                await self._flush_stale(synthesis_timers)
                continue
            except asyncio.CancelledError:
                break

            # Determine product_id for this event
            product_id = (event.metadata or {}).get("product_id") or ""
            workspace_id = (event.metadata or {}).get("workspace_id")
            if not product_id:
                logger.debug("CaptureService dropping event with no product_id")
                self._queue.task_done()
                continue

            chunker, observer, synthesizer = self._get_pipeline(product_id, workspace_id)

            # Feed event through chunker
            try:
                async for chunk, memory_id in chunker.process(_single_event_stream(event)):
                    observations = await observer.evaluate_chunk(chunk, memory_id)
                    for obs in observations:
                        obs["product"] = product_id
                        if workspace_id:
                            obs["workspace"] = workspace_id
                        await synthesizer.add_observation(obs)
                        if self._db_pool:
                            await self._write_observation(obs, product_id, workspace_id)
                    self._processed += 1
                    try:
                        from core.engine.core.metrics import capture_processed_total

                        capture_processed_total.inc()
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning("CaptureService processing error: %s", exc)

            self._queue.task_done()

            # Trigger synthesis if enough time has passed
            import time

            now = time.monotonic()
            last = synthesis_timers.get(product_id, 0)
            if now - last >= _SYNTHESIS_INTERVAL and synthesizer.pending_count > 0:
                try:
                    await synthesizer.synthesize()
                    synthesis_timers[product_id] = now
                    logger.debug("CaptureService synthesis triggered: product=%s", product_id)
                except Exception as exc:
                    logger.warning("CaptureService synthesis failed: %s", exc)

        # Flush all synthesizers on shutdown
        logger.info("CaptureService shutting down — flushing all synthesizers")
        for product_id, synth in self._synthesizers.items():
            try:
                if synth.pending_count > 0:
                    await synth.flush()
            except Exception as exc:
                logger.warning("Flush failed for product=%s: %s", product_id, exc)

    async def _flush_stale(self, synthesis_timers: dict[str, float]) -> None:
        """Trigger synthesis for products with pending observations past interval."""
        import time

        now = time.monotonic()
        for product_id, synth in self._synthesizers.items():
            last = synthesis_timers.get(product_id, 0)
            if now - last >= _SYNTHESIS_INTERVAL and synth.pending_count > 0:
                try:
                    await synth.synthesize()
                    synthesis_timers[product_id] = now
                except Exception as exc:
                    logger.warning("Periodic synthesis failed for %s: %s", product_id, exc)

    async def _write_observation(self, obs: dict, product_id: str, workspace_id: str | None) -> None:
        """Write observation to DB. Best-effort — never raises."""
        try:
            async with self._db_pool.connection() as db:
                await db.query(
                    """
                    CREATE observation SET
                        product = <record>$product,
                        content = $content,
                        observation_type = $type,
                        confidence = $conf,
                        discipline_hint = $discipline_hint,
                        domain_hint = $domain_hint,
                        source_memory = $source_memory,
                        session_id = $session_id,
                        synthesized = false,
                        created_at = time::now()
                    """,
                    {
                        "product": product_id,
                        "workspace": workspace_id,
                        "content": obs.get("content", ""),
                        "type": obs.get("observation_type", "learning"),
                        "conf": float(obs.get("confidence", 0.5)),
                        "discipline_hint": obs.get("discipline_hint", obs.get("domain_hint")),
                        "domain_hint": obs.get("domain_hint"),
                        "source_memory": obs.get("source_memory"),
                        "session_id": obs.get("session_id"),
                    },
                )
        except Exception as exc:
            logger.debug("Observation write failed: %s", exc)

    def start(self, db_pool=None) -> None:
        """Start the background processing loop. Called once at app startup."""
        if self._running:
            logger.warning("CaptureService already running")
            return
        self._db_pool = db_pool
        # Update existing pipeline components with db_pool
        for chunker in self._chunkers.values():
            chunker._db_pool = db_pool
        for synth in self._synthesizers.values():
            synth._db_pool = db_pool
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("CaptureService started (queue_max=%d interval=%ds)", _QUEUE_MAX, _SYNTHESIS_INTERVAL)

    async def stop(self) -> None:
        """Gracefully stop the service. Called at app shutdown."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(
            "CaptureService stopped: emitted=%d dropped=%d processed=%d",
            self._emitted,
            self._dropped,
            self._processed,
        )

    def get_stats(self) -> dict:
        """Return service health metrics."""
        return {
            "running": self._running,
            "queue_depth": self._queue.qsize(),
            "queue_max": _QUEUE_MAX,
            "emitted": self._emitted,
            "dropped": self._dropped,
            "processed": self._processed,
            "active_products": len(self._chunkers),
            "pending_synthesis": {pid: s.pending_count for pid, s in self._synthesizers.items()},
        }


async def _single_event_stream(event: StreamEvent):
    """Yield a single event as an async iterator for the Chunker."""
    yield event


# Module-level singleton — imported by all producers
capture_service = CaptureService()
