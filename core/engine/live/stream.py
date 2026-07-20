"""LIVE layer SSE stream — pushes real-time state changes to the portal.

Uses polling fallback (2s) on LIVE layer tables. Upgrade to SurrealDB
LIVE queries when SDK pool integration is proven.
"""

from __future__ import annotations

import asyncio
import json
import logging

from core.engine.core.db import parse_rows, pool, serialize_record

logger = logging.getLogger(__name__)


async def live_event_generator(product_id: str):
    """Yield SSE events for LIVE layer state changes."""
    last_agents = {}
    last_edits = {}
    last_locks = {}
    last_badges = ""

    while True:
        try:
            async with pool.connection() as db:
                agents = parse_rows(
                    await db.query(
                        """SELECT id, state, work_item, progress_pct, capabilities_touched
                    FROM agent_session WHERE product = <record>$product
                      AND state NOT IN ['done', 'failed', 'abandoned']""",
                        {"product": product_id},
                    )
                )
                edits = parse_rows(
                    await db.query(
                        """SELECT id, state, file, agent_session
                    FROM active_edit WHERE product = <record>$product
                      AND state NOT IN ['released', 'abandoned']""",
                        {"product": product_id},
                    )
                )
                locks = parse_rows(
                    await db.query(
                        """SELECT id, state, resource_type, resource_id, held_by
                    FROM resource_lock WHERE product = <record>$product
                      AND state IN ['acquired', 'held']""",
                        {"product": product_id},
                    )
                )
                badge_rows = parse_rows(
                    await db.query(
                        """SELECT project, tier, count() as cnt FROM notification
                           WHERE product = <record>$product AND read = false AND dismissed = false
                           GROUP BY project, tier""",
                        {"product": product_id},
                    )
                )

            # Diff and yield changes for agents
            current_agents = {str(a.get("id", "")): serialize_record(a) for a in agents}
            for sid, data in current_agents.items():
                if sid not in last_agents or last_agents[sid] != data:
                    yield {"event": "agent.state_changed", "data": json.dumps(data, default=str)}
            for sid in set(last_agents) - set(current_agents):
                yield {"event": "agent.state_changed", "data": json.dumps({"id": sid, "state": "removed"})}
            last_agents = current_agents

            # Diff and yield changes for edits
            current_edits = {str(e.get("id", "")): serialize_record(e) for e in edits}
            for eid, data in current_edits.items():
                if eid not in last_edits or last_edits[eid] != data:
                    yield {"event": "edit.state_changed", "data": json.dumps(data, default=str)}
            for eid in set(last_edits) - set(current_edits):
                yield {"event": "edit.state_changed", "data": json.dumps({"id": eid, "state": "removed"})}
            last_edits = current_edits

            # Diff and yield changes for locks
            current_locks = {str(lk.get("id", "")): serialize_record(lk) for lk in locks}
            for lid, data in current_locks.items():
                if lid not in last_locks or last_locks[lid] != data:
                    yield {"event": "lock.state_changed", "data": json.dumps(data, default=str)}
            for lid in set(last_locks) - set(current_locks):
                yield {"event": "lock.state_changed", "data": json.dumps({"id": lid, "state": "removed"})}
            last_locks = current_locks

            # Diff and yield badge changes (raw grouped counts — frontend computes severity)
            try:
                badge_json = json.dumps(badge_rows, default=str)
                if badge_json != last_badges:
                    yield {"event": "badge.updated", "data": badge_json}
                    last_badges = badge_json
            except Exception:
                pass

        except Exception as exc:
            logger.warning("LIVE stream poll error: %s", exc)

        await asyncio.sleep(2)
