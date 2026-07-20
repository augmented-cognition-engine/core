"""Bus subscribers for voice thread state transitions.

Listens for canvas resolution/reopen/answer events and updates voice_thread.status
+ appends to voice_thread_event audit log.

Registered in register_voice_stream() via register_voice_transitions().
"""

from __future__ import annotations

import logging

from core.engine.core.db import pool
from core.engine.voice.thread import read_voice_thread
from core.engine.voice.thread_event import write_thread_event

logger = logging.getLogger(__name__)


async def _transition_thread_status(
    product_id: str,
    topic: str,
    new_status: str,
    event_kind: str,
    details: dict | None = None,
) -> None:
    """Look up the thread for (product_id, topic) and transition its status."""
    thread = await read_voice_thread(product_id, topic)
    if thread is None:
        logger.debug("_transition_thread_status: no thread for (%s, %s) — skipping", product_id, topic)
        return

    await write_thread_event(thread, kind=event_kind, details=details or {})

    async with pool.connection() as db:
        await db.query(
            """UPDATE <record>$tid SET
                status = <string>$status,
                last_state_changed_at = time::now()
            """,
            {"tid": thread.id, "status": new_status},
        )
    logger.debug("_transition_thread_status: %s → %s for topic=%s", thread.status, new_status, topic)


async def on_recommendation_resolved(event_type: str, payload: dict) -> None:
    """canvas.recommendation.resolved → open thread for that topic → resolved."""
    if event_type != "canvas.recommendation.resolved":
        return
    product_id = payload.get("product_id")
    pillar = payload.get("top_pillar", "")
    discipline = payload.get("top_discipline", "")
    if not product_id or not pillar or not discipline:
        return
    topic = f"rec:{pillar}.{discipline}"
    await _transition_thread_status(
        product_id,
        topic,
        new_status="resolved",
        event_kind="resolved",
        details={"reason": payload.get("reason", "event_driven")},
    )


async def on_recommendation_reopened(event_type: str, payload: dict) -> None:
    """canvas.recommendation.reopened → resolved thread for that topic → open."""
    if event_type != "canvas.recommendation.reopened":
        return
    product_id = payload.get("product_id")
    pillar = payload.get("top_pillar", "")
    discipline = payload.get("top_discipline", "")
    if not product_id or not pillar or not discipline:
        return
    topic = f"rec:{pillar}.{discipline}"
    await _transition_thread_status(
        product_id,
        topic,
        new_status="open",
        event_kind="reopened",
        details={"days_since_resolved": payload.get("days_since_resolved")},
    )


async def on_uncertainty_answered(event_type: str, payload: dict) -> None:
    """canvas.uncertainty.answered → open uncertainty thread → resolved."""
    if event_type != "canvas.uncertainty.answered":
        return
    product_id = payload.get("product_id")
    query_id = payload.get("query_id")
    if not product_id or not query_id:
        return
    topic = f"uncertainty:{query_id}"
    await _transition_thread_status(
        product_id,
        topic,
        new_status="resolved",
        event_kind="answered",
        details={"query_id": query_id},
    )


def register_voice_transitions() -> None:
    """Register bus subscribers for thread state transitions. Called once at app startup."""
    from core.engine.events.bus import bus

    bus.on("canvas.recommendation.resolved", on_recommendation_resolved)
    bus.on("canvas.recommendation.reopened", on_recommendation_reopened)
    bus.on("canvas.uncertainty.answered", on_uncertainty_answered)
