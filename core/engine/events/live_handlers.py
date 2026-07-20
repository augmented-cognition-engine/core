"""LIVE layer event handlers — real-time coordination events."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def on_agent_state_changed(event_type: str, payload: dict) -> None:
    """Create observation when agent completes or fails."""
    new_state = payload.get("new_state", "")
    if new_state not in ("done", "failed", "abandoned"):
        return

    product_id = payload.get("product_id", "")
    session_id = payload.get("session_id", "")
    work_item = payload.get("work_item", "")

    try:
        from core.engine.core.db import pool

        obs_type = "discovery" if new_state == "done" else "failure"
        content = (
            f"Agent session {session_id} {new_state}. "
            f"Work item: {work_item}. "
            f"Capabilities: {payload.get('capabilities', [])}"
        )

        async with pool.connection() as db:
            await db.query(
                """CREATE observation SET
                    product = <record>$product, content = $content,
                    observation_type = $obs_type, confidence = 0.7,
                    discipline_hint = 'architecture', domain_hint = 'architecture',
                    source = 'agent_lifecycle', synthesized = false,
                    created_at = time::now()""",
                {"product": product_id, "content": content, "obs_type": obs_type},
            )
        logger.info("Agent %s: session %s -> %s", new_state, session_id, work_item)
    except Exception as exc:
        logger.warning("on_agent_state_changed failed: %s", exc)


async def on_edit_conflict_detected(event_type: str, payload: dict) -> None:
    """Notify PM and pause lower-priority agent when edits conflict."""
    product_id = payload.get("product_id", "")
    file_path = payload.get("file", "")

    try:
        from core.engine.notifications.dispatcher import dispatch

        await dispatch(
            product_id=product_id,
            user_id="user:default",
            tier="actionable",
            category="edit_conflict",
            title=f"Edit conflict on {file_path}",
            body="Two agents are editing the same file. Lower-priority agent paused.",
            link="/work",
        )
    except Exception as exc:
        logger.warning("on_edit_conflict_detected failed: %s", exc)
