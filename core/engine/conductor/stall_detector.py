"""StallDetector — periodic stall detection and LLM-driven reflection.

Called by Conductor on every heartbeat. Fires every 6th beat (~60 min).
Detects stuck capability_lifecycle_track rows, runs LLM reflection,
captures observations, and emits conductor.stall_detected events.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.engine.capture.service import capture_service
from core.engine.capture.watchers import StreamEvent
from core.engine.core.config import settings
from core.engine.core.db import parse_one, parse_rows
from core.engine.core.llm import get_llm
from core.engine.events.bus import bus

logger = logging.getLogger(__name__)


class StallDetector:
    """Detect stalled tracks and intervene with LLM reflection."""

    # Per-state stall thresholds (hours). Also used as the re-detection cooldown.
    # A track is stalled when it has been in the given state for longer than this threshold.
    STALL_THRESHOLDS: dict[str, int] = {
        "spec_pending": 2,
        "spec_review": 4,
        "executing": 6,
        "verifying": 4,
    }

    def __init__(self, db_pool) -> None:
        self._pool = db_pool
        self._heartbeat_count = 0

    async def maybe_check(self, product_id: str) -> bool:
        """Called every heartbeat. Fires every 6th beat (~60 min; first at T+60)."""
        self._heartbeat_count += 1
        if self._heartbeat_count % 6 != 0:
            return False
        await self._run_check(product_id)
        return True

    async def _run_check(self, product_id: str) -> None:
        """Orchestrate: detect → increment → reflect → capture → emit."""
        try:
            stuck = await self._detect_stuck_tracks(product_id)
        except Exception as exc:
            logger.error("detect_stuck_tracks failed: %s", exc)
            return

        for track in stuck:
            try:
                await self._process_stuck_track(track, product_id)
            except Exception as exc:
                logger.error("Stall processing failed for track %s: %s", track.get("id"), exc)

    async def _process_stuck_track(self, track: dict, product_id: str) -> None:
        """Full stall intervention pipeline for one track."""
        track_id = str(track.get("id", ""))
        capability_slug = track.get("capability_slug", "unknown")
        dimension = track.get("dimension", "")
        state = track.get("state", "")
        stuck_since = track.get("stuck_since")
        hours_stuck = _hours_since(stuck_since)

        spec = await self._fetch_spec(track)
        current_count = track.get("stall_count") or 0
        new_count = await self._increment_stall_count(track_id, current_count)
        reflection = await self._reflect_on_stall(track, spec)
        await self._capture_observation(track, reflection, product_id)

        payload = {
            "product_id": product_id,
            "track_id": track_id,
            "capability_slug": capability_slug,
            "dimension": dimension,
            "state": state,
            "hours_stuck": hours_stuck,
            "stall_count": new_count,
            "reflection": reflection,
        }
        try:
            await bus.emit("conductor.stall_detected", payload)
        except Exception as exc:
            logger.error("Failed to emit conductor.stall_detected for %s: %s", track_id, exc)

    async def _detect_stuck_tracks(self, product_id: str) -> list[dict]:
        """Tracks stuck past their per-state threshold, not re-detected within that same window."""
        state_clauses = " OR ".join(
            f"(state = '{state}' AND stuck_since < time::now() - {hours}h"
            f" AND (stall_last_detected_at IS NONE OR stall_last_detected_at < time::now() - {hours}h))"
            for state, hours in self.STALL_THRESHOLDS.items()
        )
        async with self._pool.connection() as db:
            result = await db.query(
                f"""
                SELECT *, capability.slug as capability_slug
                FROM capability_lifecycle_track
                WHERE product = <record>$product
                  AND stuck_since IS NOT NONE
                  AND ({state_clauses})
                ORDER BY stuck_since ASC
                LIMIT 10
                """,
                {"product": product_id},
            )
        return parse_rows(result)

    async def _fetch_spec(self, track: dict) -> dict | None:
        """Fetch linked spec record. Returns None if no active_spec_id or fetch fails."""
        spec_id = track.get("active_spec_id")
        if not spec_id:
            return None
        try:
            async with self._pool.connection() as db:
                result = await db.query(
                    "SELECT * FROM <record>$spec_id",
                    {"spec_id": str(spec_id)},
                )
            return parse_one(result)
        except Exception as exc:
            logger.debug("Spec fetch failed (non-fatal): %s", exc)
            return None

    async def _increment_stall_count(self, track_id: str, current_count: int) -> int:
        """Increment stall_count and set stall_last_detected_at. Never touches stuck_since."""
        new_count = current_count + 1
        try:
            async with self._pool.connection() as db:
                await db.query(
                    "UPDATE <record>$track_id SET stall_count = $count, stall_last_detected_at = time::now()",
                    {"track_id": track_id, "count": new_count},
                )
        except Exception as exc:
            logger.warning("Failed to increment stall_count for %s: %s", track_id, exc)
        return new_count

    async def _reflect_on_stall(self, track: dict, spec: dict | None) -> str:
        """Run LLM reflection on the stuck track. Returns '' on failure."""
        capability_name = track.get("capability_slug", "unknown")
        dimension = track.get("dimension", "")
        state = track.get("state", "")
        stuck_since = track.get("stuck_since")
        prior_stall_count = track.get("stall_count") or 0
        hours_stuck = _hours_since(stuck_since)
        spec_text = spec.get("description", "")[:500] if spec else "no spec available"

        prompt = (
            f"You are a PM reviewing a stalled initiative.\n\n"
            f"Capability: {capability_name} ({dimension} discipline)\n"
            f"State: stuck in '{state}' for {hours_stuck:.1f}h\n"
            f"Spec: {spec_text}\n"
            f"Previous stalls: {prior_stall_count}\n\n"
            f"What likely caused this stall? What should change in the next attempt?\n"
            f"Reply in 2-3 sentences."
        )

        try:
            llm = get_llm()
            return await llm.complete(prompt, model=settings.llm_budget_model)
        except Exception as exc:
            logger.warning("LLM reflection failed for track %s: %s", track.get("id"), exc)
            return ""

    async def _capture_observation(self, track: dict, reflection: str, product_id: str) -> None:
        """Write stall observation to capture pipeline (best-effort). Skipped if reflection empty."""
        if not reflection:
            return
        capability_slug = track.get("capability_slug", "unknown")
        dimension = track.get("dimension", "")
        content = f"Stall detected on {capability_slug} ({dimension}): {reflection}"
        try:
            await capture_service.emit(
                StreamEvent(
                    timestamp=datetime.now(timezone.utc),
                    event_type="tool_result",
                    content=content,
                    session_id=str(track.get("id", "")),
                    metadata={
                        "product_id": product_id,
                        "source": "conductor_stall_detector",
                        "discipline_hint": dimension,
                        "observation_type": "pattern",
                        "confidence": 0.7,
                    },
                )
            )
        except Exception as exc:
            logger.warning("Capture observation failed (best-effort): %s", exc)


def _hours_since(dt: datetime | None) -> float:
    """Return hours elapsed since dt, or 0.0 if None."""
    if dt is None:
        return 0.0
    now = datetime.now(timezone.utc)
    if isinstance(dt, datetime):
        return (now - dt).total_seconds() / 3600
    return 0.0
