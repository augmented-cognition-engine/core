# engine/worker/session.py
"""SessionManager — tracks conversation context across messages in SurrealDB."""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_rows, pool

logger = logging.getLogger(__name__)

_MAX_BUFFER = 20  # keep last N messages in rolling buffer


class SessionManager:
    """Track conversation context across messages.

    Stores session state in SurrealDB ace_session table. One row per session,
    updated on every message. ``source`` identifies the originating tool
    (e.g. "claude_code", "cursor") and is set on first message.
    """

    async def on_message(
        self,
        session_id: str,
        message: str,
        product_id: str,
        source: str = "claude_code",
    ) -> int:
        """Record an incoming message and update session state.

        Returns the new ``message_count`` — the sequence number of THIS message —
        so the caller can tag classifications and reject out-of-order results
        (see ``update_classification`` seq guard). Returns 0 on failure.
        """
        try:
            async with pool.connection() as db:
                # UPSERT: create on first message, increment counter on subsequent ones.
                # source is set on first message and preserved (never overwritten).
                result = await db.query(
                    """
                    UPSERT type::record('ace_session', $session_id) SET
                        session_id = $session_id,
                        product = $product,
                        source = source ?? $source,
                        message_count = (message_count ?? 0) + 1,
                        message_buffer = array::slice(
                            array::push(message_buffer ?? [], $message),
                            -$max_buffer
                        ),
                        classification = classification ?? {},
                        last_message_at = time::now(),
                        started_at = started_at ?? time::now()
                    """,
                    {
                        "session_id": session_id,
                        "product": product_id,
                        "source": source,
                        "message": message[:2000],
                        "max_buffer": _MAX_BUFFER,
                    },
                )
            row = parse_one(result)
            if row:
                return int(row.get("message_count", 0))
        except Exception as exc:
            logger.warning("SessionManager.on_message failed: %s", exc)
        return 0

    async def get_or_create(self, session_id: str, product_id: str) -> dict:
        """Return current session state dict, creating a minimal record if none exists."""
        try:
            async with pool.connection() as db:
                result = await db.query(
                    "SELECT * FROM type::record('ace_session', $session_id)",
                    {"session_id": session_id},
                )
                row = parse_one(result)
                if row:
                    return row
        except Exception as exc:
            logger.warning("SessionManager.get_or_create read failed: %s", exc)

        return {
            "session_id": session_id,
            "product": product_id,
            "message_count": 0,
            "rolling_summary": "",
            "compact_index": "",
            "current_discipline": "architecture",
            "current_mode": "reactive",
            "current_depth": 1,
            "classification": {},
        }

    async def update_classification(self, session_id: str, classification: dict, seq: int | None = None) -> None:
        """Persist a classification result for this session.

        When ``seq`` (the message_count this classification is for) is given,
        apply it only if it is at least as new as what is already stored — a slow
        background classify(N) must never clobber a newer provisional/refined
        classify(N+1). The guard is expressed per-field inside a single UPSERT so
        two interleaved background tasks can't race between a read and a write.
        ``seq=None`` keeps the old unconditional behaviour for any legacy caller.
        """
        params = {
            "session_id": session_id,
            "cls": classification,
            "discipline": classification.get("discipline", "architecture"),
            "mode": classification.get("mode", "reactive"),
            "depth": classification.get("depth", 1),
        }
        try:
            async with pool.connection() as db:
                if seq is None:
                    await db.query(
                        """
                        UPSERT type::record('ace_session', $session_id) SET
                            classification = $cls,
                            current_discipline = $discipline,
                            current_mode = $mode,
                            current_depth = $depth,
                            last_message_at = time::now()
                        """,
                        params,
                    )
                else:
                    params["seq"] = seq
                    await db.query(
                        """
                        UPSERT type::record('ace_session', $session_id) SET
                            classification = IF $seq >= (classification_seq ?? -1) THEN $cls ELSE classification END,
                            current_discipline = IF $seq >= (classification_seq ?? -1) THEN $discipline ELSE current_discipline END,
                            current_mode = IF $seq >= (classification_seq ?? -1) THEN $mode ELSE current_mode END,
                            current_depth = IF $seq >= (classification_seq ?? -1) THEN $depth ELSE current_depth END,
                            classification_seq = IF $seq >= (classification_seq ?? -1) THEN $seq ELSE classification_seq END,
                            last_message_at = time::now()
                        """,
                        params,
                    )
        except Exception as exc:
            logger.warning("SessionManager.update_classification failed: %s", exc)

    async def update_compact_index(self, session_id: str, compact_index: str) -> None:
        """Persist a new compact intelligence index for injection by the hook."""
        try:
            async with pool.connection() as db:
                await db.query(
                    """
                    UPSERT type::record('ace_session', $session_id) SET
                        compact_index = $compact_index,
                        last_message_at = time::now()
                    """,
                    {"session_id": session_id, "compact_index": compact_index},
                )
        except Exception as exc:
            logger.warning("SessionManager.update_compact_index failed: %s", exc)

    async def get_rolling_summary(self, session_id: str) -> str:
        """Return the rolling summary for this session (empty string if none)."""
        try:
            async with pool.connection() as db:
                result = await db.query(
                    "SELECT VALUE rolling_summary FROM type::record('ace_session', $session_id)",
                    {"session_id": session_id},
                )
                rows = parse_rows(result)
                return rows[0] if rows and isinstance(rows[0], str) else ""
        except Exception as exc:
            logger.warning("SessionManager.get_rolling_summary failed: %s", exc)
            return ""

    async def mark_complete(self, session_id: str) -> None:
        """Mark a session as complete (called by SessionEnd hook)."""
        try:
            async with pool.connection() as db:
                await db.query(
                    """
                    UPSERT type::record('ace_session', $session_id) SET
                        completed_at = time::now()
                    """,
                    {"session_id": session_id},
                )
        except Exception as exc:
            logger.warning("SessionManager.mark_complete failed: %s", exc)


session_manager = SessionManager()
