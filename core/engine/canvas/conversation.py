"""Load and persist canvas session conversation history.

Not a memory replacement for the graph. This is a flat session log:
useful for replay and for assembling context before pipeline invocation.
The graph remains the authoritative memory — decisions, capabilities,
calibration, insights all live there.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)


async def save_message(
    session_id: str,
    role: str,
    content: str,
    run_id: str | None = None,
) -> str | None:
    """Persist a user or ACE message; return the new record id."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                """CREATE conversation_message SET
                    session_id = <record>$sid,
                    role       = $role,
                    content    = $content,
                    run_id     = $run_id,
                    created_at = time::now()
                """,
                {"sid": session_id, "role": role, "content": content, "run_id": run_id},
            )
        row = parse_one(result)
        return str(row["id"]) if row else None
    except Exception:
        logger.warning("save_message failed for session %s", session_id, exc_info=True)
        return None


async def load_recent_messages(session_id: str, limit: int = 20) -> list[dict]:
    """Return the most recent N messages for a session, oldest first."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                """SELECT * FROM conversation_message
                   WHERE session_id = <record>$sid
                   ORDER BY created_at ASC
                   LIMIT $limit""",
                {"sid": session_id, "limit": limit},
            )
        return parse_rows(result)
    except Exception:
        logger.warning("load_recent_messages failed for session %s", session_id, exc_info=True)
        return []


async def save_turn(
    session_id: str,
    run_id: str,
    user_message_id: str,
    synthesis_message_id: str | None = None,
    decision_ids: list[str] | None = None,
    prediction_ids: list[str] | None = None,
) -> str | None:
    """Persist a completed conversation turn; return the turn record id."""
    try:
        async with pool.connection() as db:
            result = await db.query(
                """CREATE conversation_turn SET
                    session_id           = <record>$sid,
                    run_id               = $run_id,
                    user_message_id      = $user_msg,
                    synthesis_message_id = $synth_msg,
                    decision_ids         = $decisions,
                    prediction_ids       = $predictions,
                    created_at           = time::now()
                """,
                {
                    "sid": session_id,
                    "run_id": run_id,
                    "user_msg": user_message_id,
                    "synth_msg": synthesis_message_id,
                    "decisions": decision_ids or [],
                    "predictions": prediction_ids or [],
                },
            )
        row = parse_one(result)
        return str(row["id"]) if row else None
    except Exception:
        logger.warning("save_turn failed for session %s", session_id, exc_info=True)
        return None
