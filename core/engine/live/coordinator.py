"""Agent session coordinator — manages LIVE layer agent_session lifecycle.

Creates sessions, handles state transitions, sends heartbeats,
runs recovery sweeps for abandoned sessions.
"""

from __future__ import annotations

import logging

from core.engine.core.db import parse_one, parse_rows
from core.engine.events.bus import bus
from core.engine.live.state_machines import AgentSessionMachine, InvalidTransition

logger = logging.getLogger(__name__)


class AgentCoordinator:
    def __init__(self, db_pool):
        self._pool = db_pool

    async def start_session(
        self,
        product_id: str,
        work_item_id: str | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Create a new agent_session in 'starting' state."""
        async with self._pool.connection() as db:
            # Use conditional user cast so null user_id doesn't cause a type error
            user_sql = "user = <record>$user," if user_id else ""
            result = await db.query(
                f"""CREATE agent_session SET
                    product = <record>$product,
                    work_item = $work_item,
                    {user_sql}
                    state = 'starting',
                    started_at = time::now(),
                    last_heartbeat = time::now()""",
                {
                    "product": product_id,
                    "work_item": work_item_id,
                    "user": user_id,
                },
            )
            session = parse_one(result)

        if session:
            await bus.emit(
                "agent.state_changed",
                {
                    "product_id": product_id,
                    "session_id": str(session.get("id", "")),
                    "old_state": "",
                    "new_state": "starting",
                    "work_item": work_item_id or "",
                    "capabilities": [],
                },
            )

        return session or {"state": "starting"}

    async def transition(self, session_id: str, target_state: str) -> dict:
        """Transition an agent_session to a new state."""
        async with self._pool.connection() as db:
            result = await db.query(
                "SELECT * FROM ONLY <record>$id",
                {"id": session_id},
            )
            session = parse_one(result)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            current = session.get("state", "")
            machine = AgentSessionMachine(current)
            machine.transition(target_state)  # raises InvalidTransition if invalid

            update_fields = "state = $state, last_heartbeat = time::now()"
            if target_state in ("done", "failed", "abandoned"):
                update_fields += ", completed_at = time::now()"

            result = await db.query(
                f"UPDATE <record>$id SET {update_fields}",
                {"id": session_id, "state": target_state},
            )
            updated = parse_one(result)

        await bus.emit(
            "agent.state_changed",
            {
                "product_id": str(session.get("product", "")),
                "session_id": session_id,
                "old_state": current,
                "new_state": target_state,
                "work_item": str(session.get("work_item", "")),
                "capabilities": session.get("capabilities_touched", []),
            },
        )

        return updated or {"id": session_id, "state": target_state}

    async def heartbeat(self, session_id: str, progress_pct: int | None = None) -> None:
        """Update heartbeat timestamp for an active session."""
        async with self._pool.connection() as db:
            if progress_pct is not None:
                await db.query(
                    "UPDATE <record>$id SET last_heartbeat = time::now(), progress_pct = $pct",
                    {"id": session_id, "pct": progress_pct},
                )
            else:
                await db.query(
                    "UPDATE <record>$id SET last_heartbeat = time::now()",
                    {"id": session_id},
                )

    async def recover_abandoned(self, product_id: str, stale_minutes: int = 3) -> int:
        """Transition sessions with no heartbeat for stale_minutes to 'abandoned'."""
        async with self._pool.connection() as db:
            stale = parse_rows(
                await db.query(
                    """SELECT id, state, work_item, capabilities_touched
                FROM agent_session
                WHERE product = <record>$product
                  AND state IN ['starting', 'active', 'blocked', 'completing']
                  AND last_heartbeat < time::now() - type::duration($dur)""",
                    {"product": product_id, "dur": f"{stale_minutes}m"},
                )
            )

        count = 0
        for session in stale:
            try:
                await self.transition(str(session["id"]), "abandoned")
                count += 1
            except (InvalidTransition, Exception) as exc:
                logger.warning("Failed to abandon session %s: %s", session.get("id"), exc)

        if count:
            logger.info("Recovered %d abandoned sessions for %s", count, product_id)
        return count

    async def get_active_sessions(self, product_id: str) -> list[dict]:
        """Get all non-terminal sessions for an org."""
        async with self._pool.connection() as db:
            result = await db.query(
                """SELECT * FROM agent_session
                WHERE product = <record>$product
                  AND state IN ['starting', 'active', 'blocked', 'completing']
                ORDER BY started_at DESC""",
                {"product": product_id},
            )
            return parse_rows(result)

    async def update_files_claimed(self, session_id: str, file_paths: list[str]) -> None:
        """Update the files_claimed array on a session."""
        async with self._pool.connection() as db:
            await db.query(
                "UPDATE <record>$id SET files_claimed = $files",
                {"id": session_id, "files": file_paths},
            )

    async def update_capabilities_touched(self, session_id: str, capability_slugs: list[str]) -> None:
        """Update the capabilities_touched array on a session."""
        async with self._pool.connection() as db:
            await db.query(
                "UPDATE <record>$id SET capabilities_touched = $caps",
                {"id": session_id, "caps": capability_slugs},
            )
