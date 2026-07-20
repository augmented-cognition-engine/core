# engine/capture/pipeline.py
"""CapturePipeline — wires Chunker, Observer, and Synthesizer together.

Runs as an async process for the life of a session.
Handles periodic synthesis timer and final flush.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from core.engine.capture.chunker import Chunker

logger = logging.getLogger(__name__)
from core.engine.capture.observer import Observer
from core.engine.capture.synthesizer import Synthesizer
from core.engine.capture.watchers import StreamWatcher

if TYPE_CHECKING:
    from core.engine.session.models import Session


class CapturePipeline:
    """Wires together all capture stages."""

    def __init__(
        self,
        watcher: StreamWatcher,
        product_id: str,
        workspace_id: str | None,
        synthesis_interval: int = 900,  # 15 minutes
        db_pool=None,
        discipline_hint: str | None = None,
        session: "Session | None" = None,
    ) -> None:
        self.watcher = watcher
        self.chunker = Chunker()
        self.observer = Observer(product_id, workspace_id, discipline_hint=discipline_hint)
        self.synthesizer = Synthesizer(product_id, workspace_id)
        self._synthesis_interval = synthesis_interval
        self._running = False
        self._db_pool = db_pool
        self._observations_written = 0
        self._observations_skipped = 0
        self._discipline_hint = discipline_hint
        # Source-agnostic session context — set when a Session is provided
        self._session = session
        self._session_source: str = session.source if session else "claude_code"
        # Wire db_pool to chunker and synthesizer
        if db_pool:
            self.chunker._db_pool = db_pool
            self.chunker._org_id = product_id
            self.synthesizer._db_pool = db_pool

    def _validate_observation(self, obs: dict) -> None:
        """Validate an observation dict before writing to the database.

        Raises ValueError if required fields are missing or have invalid values.
        Called by _write_observation to catch malformed observations early and
        prevent corrupt records from entering the synthesis pipeline.
        """
        if not obs.get("content", "").strip():
            raise ValueError("observation.content must be non-empty")
        if not obs.get("product"):
            raise ValueError("observation.product must be set")
        confidence = obs.get("confidence", 0.5)
        if not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(f"observation.confidence must be in [0.0, 1.0], got {confidence}")

    def get_stats(self) -> dict:
        """Return pipeline health metrics for observability."""
        return {
            "running": self._running,
            "observations_written": self._observations_written,
            "observations_skipped": self._observations_skipped,
            "pending_synthesis": self.synthesizer.pending_count,
        }

    async def _write_observation(self, obs: dict) -> str | None:
        """Write an observation dict to the observation table."""
        try:
            self._validate_observation(obs)
        except ValueError as exc:
            logger.warning("Skipping invalid observation: %s", exc)
            self._observations_skipped += 1
            return None
        if not self._db_pool:
            return None
        async with self._db_pool.connection() as db:
            result = await db.query(
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
                    session_source = $session_source,
                    synthesized = false,
                    created_at = time::now()
                """,
                {
                    "product": obs["product"],
                    "workspace": obs.get("workspace"),
                    "content": obs["content"],
                    "type": obs["observation_type"],
                    "conf": float(obs.get("confidence", 0.5)),
                    "discipline_hint": obs.get("discipline_hint", obs.get("domain_hint")),
                    "domain_hint": obs.get("domain_hint"),
                    "source_memory": obs.get("source_memory"),
                    "session_id": obs.get("session_id"),
                    "session_source": self._session_source,
                },
            )
            from core.engine.core.db import parse_one

            row = parse_one(result)
            obs_id = row.get("id") if row else None
            if obs_id:
                self._observations_written += 1
                logger.debug(
                    "Wrote observation type=%s conf=%.2f id=%s",
                    obs.get("observation_type"),
                    float(obs.get("confidence", 0.5)),
                    obs_id,
                )
            else:
                logger.warning("Observation write returned no id (type=%s)", obs.get("observation_type"))
            return obs_id

    async def _load_observer_intelligence(self) -> None:
        """Load discipline intelligence once before processing begins.

        Primes the Observer with top insights so chunk evaluation can recognize
        deviations from established patterns. Best-effort — never blocks startup.
        """
        if not self._discipline_hint or not self._db_pool:
            return
        try:
            from core.engine.orchestrator.loader import load_intelligence

            snapshot = await load_intelligence(
                discipline=self._discipline_hint,
                product_id=self.observer.product_id,
                mode="reactive",
            )
            insights = snapshot.get("insights", [])
            if insights:
                lines = [f"- [{i.get('confidence', 0):.0%}] {i.get('content', '')}" for i in insights[:6]]
                self.observer.set_intel_context("\n".join(lines))
                logger.debug("Observer primed with %d %s insights", len(lines), self._discipline_hint)
        except Exception as exc:
            logger.debug("Observer intelligence load skipped: %s", exc)

    async def run(self) -> None:
        """Start the capture pipeline. Runs until the stream ends."""
        self._running = True
        logger.info(
            "CapturePipeline started (product=%s interval=%ds)", self.observer.product_id, self._synthesis_interval
        )
        await self._load_observer_intelligence()
        timer_task = asyncio.create_task(self._periodic_synthesis())

        try:
            events = self.watcher.watch()
            async for chunk, memory_id in self.chunker.process(events):
                observations = await self.observer.evaluate_chunk(chunk, memory_id)
                for obs in observations:
                    # Write observation to DB
                    if self._db_pool:
                        await self._write_observation(obs)
                    await self.synthesizer.add_observation(obs)
        finally:
            self._running = False
            timer_task.cancel()
            try:
                await timer_task
            except asyncio.CancelledError:
                pass
            # Flush remaining observations
            logger.info("CapturePipeline stopping — flushing pending observations")
            await self.synthesizer.flush()

    async def _periodic_synthesis(self) -> None:
        """Force synthesis every N seconds during active sessions."""
        while self._running:
            await asyncio.sleep(self._synthesis_interval)
            if self.synthesizer.pending_count > 0:
                logger.debug("Periodic synthesis triggered (%d pending)", self.synthesizer.pending_count)
                await self.synthesizer.synthesize()
