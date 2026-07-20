"""Drift detector — emits canvas.drift.crossed when blocked-fraction crosses a band."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_rows, pool
from core.engine.events.bus import bus

logger = logging.getLogger(__name__)

_BANDS = [0.0, 0.3, 0.5, 0.7, 0.9, 1.0]


def compute_band(frac: float) -> int:
    """Return band index 0..N-1 for a blocked-fraction value."""
    for i, upper in enumerate(_BANDS[1:], start=0):
        if frac < upper:
            return i
    return len(_BANDS) - 2


async def on_score_changed(event_type: str, payload: dict) -> None:
    if event_type not in ("canvas.score.changed", "canvas.capability.added"):
        return
    product_id = payload.get("product_id")
    if not product_id:
        return
    await _maybe_emit_drift(product_id)


async def _maybe_emit_drift(product_id: str) -> None:
    """Recompute blocked-fraction; if band changed from persisted state, emit."""
    from core.engine.sentinel.engines.briefing import build_briefing_payload

    payload = await build_briefing_payload(product_id)
    drift = payload.get("target_drift_assessment")
    if not drift or not drift.get("n_total"):
        return
    new_frac = drift["n_blocked"] / drift["n_total"]

    async with pool.connection() as db:
        rows = parse_rows(
            await db.query(
                "SELECT last_blocked_frac FROM voice_drift_state WHERE product = <record>$pid LIMIT 1",
                {"pid": product_id},
            )
        )
        prev_frac = float(rows[0]["last_blocked_frac"]) if rows else 0.0
        prev_band = compute_band(prev_frac)
        new_band = compute_band(new_frac)
        if new_band != prev_band:
            await bus.emit(
                "canvas.drift.crossed",
                {
                    "product_id": product_id,
                    "prev_blocked_frac": prev_frac,
                    "new_blocked_frac": new_frac,
                    "n_total": drift["n_total"],
                    "n_blocked": drift["n_blocked"],
                    "blocking_pillars": drift.get("blocking_pillars") or [],
                },
            )
        # Always update persisted state
        await db.query(
            """UPSERT voice_drift_state CONTENT {
                product: <record>$pid,
                last_blocked_frac: <float>$frac,
                last_computed_at: time::now()
            } WHERE product = <record>$pid""",
            {"pid": product_id, "frac": new_frac},
        )


def register_drift_detector() -> None:
    bus.on("canvas.score.changed", on_score_changed)
    bus.on("canvas.capability.added", on_score_changed)
