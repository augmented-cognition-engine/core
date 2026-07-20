# engine/pm/locks.py
"""File-level lock manager using resource_lock table with explicit lifecycle.

Prevents concurrent edits to the same files by different work items.
Uses SurrealDB UNIQUE index on (org, resource_type, resource_id) as the
concurrency primitive — a CREATE on an already-locked resource fails.

Lock lifecycle: held -> released | stolen
- acquire() creates with state='held'
- release() UPDATEs to state='released' (preserves history)
- expired locks are UPDATEd to state='stolen' when a new holder takes over
- is_locked() checks both expiry AND state
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Active lock states — is_locked() returns True only for these
_ACTIVE_STATES = ("acquired", "held")


class FileLockManager:
    """Acquire/release file-level locks via resource_lock table."""

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    def _pool(self):
        if self._db_pool:
            return self._db_pool
        from core.engine.core.db import pool

        return pool

    async def _emit_state_changed(self, payload: dict) -> None:
        """Emit lock.state_changed event. Never raises."""
        try:
            from core.engine.events.bus import bus

            await bus.emit("lock.state_changed", payload)
        except Exception:
            pass

    async def acquire(
        self,
        resource_type: str,
        resource_id: str,
        held_by: str,
        product_id: str,
        ttl_minutes: int = 60,
    ) -> bool:
        """Acquire a lock. Returns True if acquired, False if held by another."""
        from core.engine.core.db import parse_rows

        async with self._pool().connection() as db:
            # Check if an ACTIVE lock exists (ignore released/stolen records)
            existing = await db.query(
                """
                SELECT * FROM resource_lock
                WHERE product = <record>$product AND resource_type = $type AND resource_id = $rid
                  AND (state = 'held' OR state = 'acquired')
                LIMIT 1
                """,
                {"product": product_id, "type": resource_type, "rid": resource_id},
            )
            existing_rows = parse_rows(existing)
            if existing_rows:
                # Lock exists — check if expired or same holder
                return await self._try_steal_expired(db, resource_type, resource_id, held_by, product_id, ttl_minutes)

            # Remove any inactive (released/stolen) locks that would block the unique index
            await db.query(
                """
                DELETE resource_lock
                WHERE product = <record>$product AND resource_type = $type AND resource_id = $rid
                  AND state NOT IN ['held', 'acquired']
                """,
                {"product": product_id, "type": resource_type, "rid": resource_id},
            )

            result = await db.query(
                """
                CREATE resource_lock SET
                    product = <record>$product,
                    resource_type = $type,
                    resource_id = $rid,
                    held_by = $held_by,
                    state = 'held',
                    acquired_at = time::now(),
                    expires_at = time::now() + type::duration($ttl)
                """,
                {
                    "product": product_id,
                    "type": resource_type,
                    "rid": resource_id,
                    "held_by": held_by,
                    "ttl": f"{ttl_minutes}m",
                },
            )
            created = parse_rows(result)
            if created:
                await self._emit_state_changed(
                    {
                        "state": "held",
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "held_by": held_by,
                        "product_id": product_id,
                    }
                )
                return True
            # CREATE returned empty — unique index hit (active lock exists); check if expired
            return await self._try_steal_expired(db, resource_type, resource_id, held_by, product_id, ttl_minutes)

    async def _try_steal_expired(
        self,
        db,
        resource_type: str,
        resource_id: str,
        held_by: str,
        product_id: str,
        ttl_minutes: int,
    ) -> bool:
        """If the existing lock is expired, mark it stolen and re-acquire."""
        result = await db.query(
            """
            SELECT * FROM resource_lock
            WHERE product = <record>$product AND resource_type = $type AND resource_id = $rid
              AND (state = 'held' OR state = 'acquired')
            LIMIT 1
            """,
            {"product": product_id, "type": resource_type, "rid": resource_id},
        )
        from core.engine.core.db import parse_rows

        rows = parse_rows(result)
        if not rows:
            # Lock vanished — retry acquire (clean up any inactive record first)
            await db.query(
                """
                DELETE resource_lock
                WHERE product = <record>$product AND resource_type = $type AND resource_id = $rid
                  AND state NOT IN ['held', 'acquired']
                """,
                {"product": product_id, "type": resource_type, "rid": resource_id},
            )
            retry = await db.query(
                """
                CREATE resource_lock SET
                    product = <record>$product,
                    resource_type = $type,
                    resource_id = $rid,
                    held_by = $held_by,
                    state = 'held',
                    acquired_at = time::now(),
                    expires_at = time::now() + type::duration($ttl)
                """,
                {
                    "product": product_id,
                    "type": resource_type,
                    "rid": resource_id,
                    "held_by": held_by,
                    "ttl": f"{ttl_minutes}m",
                },
            )
            if parse_rows(retry):
                await self._emit_state_changed(
                    {
                        "state": "held",
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "held_by": held_by,
                        "product_id": product_id,
                    }
                )
                return True
            return False

        existing = rows[0]
        expires_at_str = existing.get("expires_at", "")
        try:
            if isinstance(expires_at_str, str):
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            else:
                expires_at = expires_at_str
            now = datetime.now(timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                # Expired — mark old lock as stolen, then create new one
                lock_id = existing.get("id", "")
                await db.query(
                    """
                    UPDATE <record>$id SET
                        state = 'stolen',
                        stolen_by = $new_holder,
                        stolen_at = time::now()
                    """,
                    {"id": lock_id, "new_holder": held_by},
                )
                logger.info("Stole expired lock %s (was held by %s)", resource_id, existing.get("held_by"))
                steal_result = await db.query(
                    """
                    CREATE resource_lock SET
                        product = <record>$product,
                        resource_type = $type,
                        resource_id = $rid,
                        held_by = $held_by,
                        state = 'held',
                        acquired_at = time::now(),
                        expires_at = time::now() + type::duration($ttl)
                    """,
                    {
                        "product": product_id,
                        "type": resource_type,
                        "rid": resource_id,
                        "held_by": held_by,
                        "ttl": f"{ttl_minutes}m",
                    },
                )
                if parse_rows(steal_result):
                    await self._emit_state_changed(
                        {
                            "state": "held",
                            "resource_type": resource_type,
                            "resource_id": resource_id,
                            "held_by": held_by,
                            "product_id": product_id,
                            "previous_holder": existing.get("held_by"),
                            "stolen": True,
                        }
                    )
                    return True
                return False
        except (ValueError, TypeError):
            pass

        return False

    async def release(
        self,
        resource_type: str,
        resource_id: str,
        product_id: str,
    ) -> None:
        """Release a specific lock by transitioning to state='released'."""
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE resource_lock SET
                    state = 'released',
                    released_at = time::now()
                WHERE product = <record>$product AND resource_type = $type AND resource_id = $rid
                    AND state IN ['acquired', 'held']
                """,
                {"product": product_id, "type": resource_type, "rid": resource_id},
            )
        await self._emit_state_changed(
            {
                "state": "released",
                "resource_type": resource_type,
                "resource_id": resource_id,
                "product_id": product_id,
            }
        )

    async def release_all(self, held_by: str, product_id: str) -> None:
        """Release all locks held by a specific work item."""
        async with self._pool().connection() as db:
            await db.query(
                """
                UPDATE resource_lock SET
                    state = 'released',
                    released_at = time::now()
                WHERE product = <record>$product AND held_by = $held_by
                    AND state IN ['acquired', 'held']
                """,
                {"product": product_id, "held_by": held_by},
            )
        await self._emit_state_changed(
            {
                "state": "released",
                "held_by": held_by,
                "product_id": product_id,
                "bulk": True,
            }
        )

    async def acquire_many(
        self,
        resource_type: str,
        resource_ids: list[str],
        held_by: str,
        product_id: str,
        ttl_minutes: int = 60,
    ) -> list[bool]:
        """Acquire locks on multiple resources. Returns list of results."""
        results = []
        for rid in resource_ids:
            result = await self.acquire(resource_type, rid, held_by, product_id, ttl_minutes)
            results.append(result)
        return results

    async def is_locked(
        self,
        resource_type: str,
        resource_id: str,
        product_id: str,
    ) -> bool:
        """Check if a resource is currently locked (active state + non-expired)."""
        from core.engine.core.db import parse_rows

        async with self._pool().connection() as db:
            result = await db.query(
                """
                SELECT * FROM resource_lock
                WHERE product = <record>$product AND resource_type = $type AND resource_id = $rid
                """,
                {"product": product_id, "type": resource_type, "rid": resource_id},
            )
            rows = parse_rows(result)
            if not rows:
                return False
            existing = rows[0]

            # Check state — must be in an active state
            state = existing.get("state", "held")  # default 'held' for legacy rows
            if state not in _ACTIVE_STATES:
                return False

            expires_at_str = existing.get("expires_at", "")
            try:
                if isinstance(expires_at_str, str):
                    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                else:
                    expires_at = expires_at_str
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                return expires_at > datetime.now(timezone.utc)
            except (ValueError, TypeError):
                return True
